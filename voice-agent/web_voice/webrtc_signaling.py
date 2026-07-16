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
from .utterance_aggregator import UtteranceAggregator
from .webrtc_support import probe_webrtc_support

DEFAULT_SAMPLE_RATE = 16000


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
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)


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
        self._sessions: dict[str, _Session] = {}

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
        envelope = ChannelEnvelope.for_web_turn()
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
        if self._streaming_provider is not None:
            return self._build_streaming_session(transport, envelope, telemetry)
        return self._build_batch_session(transport, envelope, telemetry)

    def _build_streaming_session(self, transport, envelope, telemetry) -> StreamingVoiceSession:
        stt = StreamingSttProcessor(
            self._streaming_provider,
            envelope,
            telemetry,
            provider_name=self._streaming_provider.name,
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
        )

    def _build_batch_session(self, transport, envelope, telemetry) -> StreamingVoiceSession:
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
        @connection.event_handler("closed")
        async def _on_closed(conn) -> None:  # noqa: ANN001 - pipecat callback signature
            self._discard(conn.pc_id)

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
