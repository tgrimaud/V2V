"""WebRTC signaling for the streaming voice loop (Sprint 6 / TASK-WEB-007).

Reimplements the offer→answer handshake directly on `SmallWebRTCConnection` so the
stdlib HTTP server does not need FastAPI (which the bundled
`SmallWebRTCRequestHandler` imports). For each new offer it:

1. creates a `SmallWebRTCConnection` and `initialize`s it with the browser's offer;
2. builds a `SmallWebRTCTransport` (audio in/out at 16 kHz) and a
   `StreamingVoiceSession` (with the utterance aggregator in front of the batch STT);
3. starts the session on the shared background loop (single long-lived loop, RF-012);
4. returns the SDP answer + the session correlation id.

One `ChannelEnvelope` + one `TelemetryRecorder` per connection → the US-036 slices for
every turn in a call share **one correlation id** (AC of TASK-WEB-007). Media only
starts flowing once the pipeline `StartFrame` triggers `connection.connect()`.
"""

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable

from voice_common.telemetry import TelemetryRecorder

from .async_loop import BackgroundEventLoop
from .egress import WebVoiceEgress
from .envelope import ChannelEnvelope
from .ingress import WebVoiceIngress
from .streaming_runtime import StreamingVoiceSession
from .streaming_stt_processor import StreamingSttProcessor
from .streaming_tts_processor import StreamingTtsProcessor
from .utterance_aggregator import UtteranceAggregator
from .webrtc_support import probe_webrtc_support

DEFAULT_SAMPLE_RATE = 16000


def _barge_in_config() -> dict[str, int]:
    """Read the optional anti-echo barge-in overrides from the environment.

    Returns only the keys that are set so the `StreamingSttProcessor` defaults apply
    otherwise. Invalid values are ignored (defaults win) rather than crashing a call.
    """
    config: dict[str, int] = {}
    for env_var, kwarg in (
        ("VOICE_BARGE_IN_THRESHOLD", "barge_in_amplitude_threshold"),
        ("VOICE_BARGE_IN_FRAMES", "barge_in_confirm_frames"),
    ):
        raw = os.environ.get(env_var)
        if raw is None:
            continue
        try:
            config[kwarg] = int(raw)
        except ValueError:
            continue
    return config


@dataclass
class _Session:
    connection: Any
    session: StreamingVoiceSession
    envelope: ChannelEnvelope
    telemetry: TelemetryRecorder
    task: Any = None


def _log_telemetry(telemetry: TelemetryRecorder) -> None:
    payload = {
        "spans": [span.__dict__ for span in telemetry.spans()],
        "events": [event.__dict__ for event in telemetry.events()],
        "metrics": [metric.__dict__ for metric in telemetry.metrics()],
    }
    # flush=True: the per-call telemetry dump is the only latency/QA evidence for a
    # streaming call (no HTTP response per turn). When stderr is redirected to a file
    # it is block-buffered, so without an explicit flush the dump can sit unwritten
    # until the process exits — losing the evidence for TASK-WEB-009 measurement.
    print(json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)


class WebRtcSignalingService:
    """Owns WebRTC sessions; drives offer/answer on the shared background loop."""

    def __init__(
        self,
        *,
        ingress: WebVoiceIngress,
        egress: WebVoiceEgress,
        backend: Any,
        loop: BackgroundEventLoop,
        ice_servers: list[str] | None = None,
        telemetry_factory: Callable[[], TelemetryRecorder] = TelemetryRecorder,
        log: Callable[[TelemetryRecorder], None] = _log_telemetry,
        streaming_provider: Any = None,
        streaming_tts_provider: Any = None,
        streaming_providers_by_language: dict[str, Any] | None = None,
        streaming_tts_providers_by_language: dict[str, Any] | None = None,
    ) -> None:
        support = probe_webrtc_support()
        if not support.available:
            raise RuntimeError(
                f"WebRTC runtime unavailable ({support.missing}). {support.install_hint}"
            )
        self._ingress = ingress
        self._egress = egress
        self._backend = backend
        self._loop = loop
        self._ice_servers = ice_servers or []
        self._telemetry_factory = telemetry_factory
        self._log = log
        # When set (TASK-STT-010), each session uses the streaming STT processor
        # (partials during speech, low-latency finalize) instead of the batch
        # utterance aggregator + one-shot transcription.
        self._streaming_provider = streaming_provider
        # When set (TASK-WEB-004), each session uses the streaming TTS processor
        # (incremental playback on the first chunk) instead of the batch TTS
        # processor. Independent of the STT mode, so it applies to both paths.
        self._streaming_tts_provider = streaming_tts_provider
        # US-042: per-session streaming providers keyed by language ("fr"/"en"). Empty ->
        # the single default streaming provider is used for every session.
        self._streaming_providers_by_language = {
            key.lower(): value for key, value in (streaming_providers_by_language or {}).items()
        }
        self._streaming_tts_providers_by_language = {
            key.lower(): value for key, value in (streaming_tts_providers_by_language or {}).items()
        }
        self._sessions: dict[str, _Session] = {}

    def _streaming_provider_for(self, envelope: ChannelEnvelope) -> Any:
        language = (getattr(envelope, "language", None) or "").lower()
        return self._streaming_providers_by_language.get(language, self._streaming_provider)

    def _streaming_tts_provider_for(self, envelope: ChannelEnvelope) -> Any:
        language = (getattr(envelope, "language", None) or "").lower()
        return self._streaming_tts_providers_by_language.get(language, self._streaming_tts_provider)

    def handle_offer(self, body: dict, *, timeout: float = 30.0) -> dict:
        """Blocking offer→answer for the HTTP handler (runs on the background loop)."""
        return self._loop.run(self._negotiate(body), timeout=timeout)

    async def _negotiate(self, body: dict) -> dict:
        pc_id = body.get("pc_id")
        existing = self._sessions.get(pc_id) if pc_id else None
        if existing is not None:
            return await self._renegotiate(existing, body)
        return await self._new_session(body)

    async def _renegotiate(self, record: _Session, body: dict) -> dict:
        await record.connection.renegotiate(
            sdp=body["sdp"], type=body["type"], restart_pc=bool(body.get("restart_pc"))
        )
        return self._answer_payload(record.connection.get_answer(), record.envelope)

    async def _new_session(self, body: dict) -> dict:
        import asyncio

        from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

        connection = SmallWebRTCConnection(ice_servers=self._ice_servers)
        await connection.initialize(sdp=body["sdp"], type=body["type"])
        # US-042: the UI-selected language rides on the offer body and is carried by the
        # session envelope -> forces the backend answer language and selects the STT/TTS voice.
        envelope = ChannelEnvelope.for_web_turn(language=body.get("language"))
        telemetry = self._telemetry_factory()
        session = self._build_session(connection, envelope, telemetry)
        record = _Session(connection, session, envelope, telemetry)
        self._register_cleanup(connection)
        self._sessions[connection.pc_id] = record
        answer = self._answer_payload(connection.get_answer(), envelope)
        record.task = asyncio.ensure_future(session.run())
        return answer

    def _build_session(self, connection, envelope, telemetry) -> StreamingVoiceSession:
        transport = self._build_transport(connection)
        tts_processor = self._build_tts_processor(envelope, telemetry)
        if self._streaming_provider is not None:
            return self._build_streaming_session(transport, envelope, telemetry, tts_processor)
        return self._build_batch_session(transport, envelope, telemetry, tts_processor)

    def _build_tts_processor(self, envelope, telemetry):
        """Streaming TTS processor for the session, or None (batch TTS fallback)."""
        if self._streaming_tts_provider is None:
            return None
        provider = self._streaming_tts_provider_for(envelope)
        return StreamingTtsProcessor(
            provider,
            envelope,
            telemetry,
            provider_name=provider.name,
        )

    def _build_streaming_session(
        self, transport, envelope, telemetry, tts_processor
    ) -> StreamingVoiceSession:
        provider = self._streaming_provider_for(envelope)
        stt = StreamingSttProcessor(
            provider,
            envelope,
            telemetry,
            provider_name=provider.name,
            # Anti-echo barge-in gate, tunable without a code change (TASK-WEB-008): raise
            # VOICE_BARGE_IN_THRESHOLD on echoey speaker setups so the bot's own residual
            # echo does not self-interrupt; VOICE_BARGE_IN_FRAMES sets the sustained-onset
            # count. Unset -> the processor defaults apply.
            **_barge_in_config(),
        )
        return StreamingVoiceSession(
            transport,
            ingress=self._ingress,
            egress=self._egress,
            envelope=envelope,
            backend=self._backend,
            telemetry=telemetry,
            # The streaming STT processor consumes continuous audio, owns end-of-turn
            # detection + its span and emits the final transcript itself.
            stt_processor=stt,
            tts_processor=tts_processor,
        )

    def _build_batch_session(
        self, transport, envelope, telemetry, tts_processor
    ) -> StreamingVoiceSession:
        aggregator = UtteranceAggregator(
            sample_rate_hz=DEFAULT_SAMPLE_RATE,
            telemetry=telemetry,
            envelope=envelope,
            provider_name=self._ingress.provider_name,
        )
        return StreamingVoiceSession(
            transport,
            ingress=self._ingress,
            egress=self._egress,
            envelope=envelope,
            backend=self._backend,
            telemetry=telemetry,
            pre_stt=[aggregator],
            # The aggregator owns incremental end-of-turn detection + its span on the
            # streaming path, so the batch detector in the ingress is skipped here.
            stt_detects_end_of_turn=False,
            tts_processor=tts_processor,
        )

    def _build_transport(self, connection):
        from pipecat.transports.base_transport import TransportParams
        from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

        params = TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=DEFAULT_SAMPLE_RATE,
            audio_out_sample_rate=DEFAULT_SAMPLE_RATE,
        )
        return SmallWebRTCTransport(connection, params=params)

    def _register_cleanup(self, connection) -> None:
        # SmallWebRTCConnection emits its connection-state name as the event, so a
        # clean hangup fires "closed" and an abrupt drop fires "disconnected". Register
        # both so telemetry is emitted on either teardown path; `_drain_and_discard` is
        # idempotent (the second event finds the session already popped).
        @connection.event_handler("closed")
        async def _on_closed(conn) -> None:  # noqa: ANN001 - pipecat callback signature
            await self._drain_and_discard(conn.pc_id)

        @connection.event_handler("disconnected")
        async def _on_disconnected(conn) -> None:  # noqa: ANN001 - pipecat callback signature
            await self._drain_and_discard(conn.pc_id)

    async def _drain_and_discard(self, pc_id: str) -> None:
        """On call end/drop: flush a trailing partial utterance (TASK-WEB-008) before
        discarding, so a customer still mid-speech at hangup still yields an
        end_of_turn span + final transcript in telemetry instead of a silently
        dropped turn. Draining is best-effort; teardown always proceeds.
        """
        record = self._sessions.get(pc_id)
        if record is not None:
            await self._drain(record)
        self._discard(pc_id)

    async def _drain(self, record: _Session, timeout: float = 5.0) -> None:
        import asyncio

        # Best-effort graceful flush that must NEVER block the telemetry dump. On a
        # `closed`/`disconnected` connection the transport is already dead, so the
        # EndFrame queued by `drain()` (stop_when_done) can never reach the transport
        # output and the coroutine hangs — and because it is stuck in an uncancellable
        # await, `wait_for` would itself hang awaiting the cancellation. So we wait with
        # `asyncio.wait` (which returns on timeout without awaiting the pending task) and
        # then cancel fire-and-forget, guaranteeing we always reach `_discard`/telemetry.
        drain_task = asyncio.ensure_future(record.session.drain())
        try:
            _, pending = await asyncio.wait({drain_task}, timeout=timeout)
        except Exception:  # noqa: BLE001 - teardown must not fail
            pending = {drain_task}
        for task in pending:
            task.cancel()
        if pending and record.task is not None:
            # The session run() task is stuck behind the same dead transport; stop it
            # fire-and-forget so the loop is not leaked (server close() also reaps it).
            record.task.cancel()

    def _discard(self, pc_id: str) -> None:
        record = self._sessions.pop(pc_id, None)
        if record is not None:
            self._log(record.telemetry)

    def _answer_payload(self, answer: dict | None, envelope: ChannelEnvelope) -> dict:
        if answer is None:
            raise RuntimeError("SmallWebRTC connection produced no SDP answer")
        return {**answer, "correlation_id": envelope.correlation_id}

    def close(self) -> None:
        """Tear down all live sessions (stop pipeline, disconnect) on server shutdown."""
        for record in list(self._sessions.values()):
            try:
                self._loop.run(self._teardown(record), timeout=10)
            except Exception:  # noqa: BLE001 - best-effort teardown per session
                pass
        self._sessions.clear()

    async def _teardown(self, record: _Session) -> None:
        import asyncio

        await record.session.stop()
        await record.connection.disconnect()
        if record.task is not None:
            try:
                await asyncio.wait_for(record.task, timeout=5)
            except Exception:  # noqa: BLE001 - the session task ends via cancellation
                pass
