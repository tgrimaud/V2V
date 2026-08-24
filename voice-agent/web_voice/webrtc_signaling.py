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

from voice_common.otel_export import export_recorder
from voice_common.telemetry import TelemetryRecorder

from .async_loop import BackgroundEventLoop
from .egress import WebVoiceEgress
from .envelope import ChannelEnvelope
from .error_response import SessionCapacityError
from .ingress import WebVoiceIngress
from .session_factory import (  # noqa: F401 - re-exported for backward-compat test imports
    DEFAULT_SAMPLE_RATE,
    PILOT_END_OF_TURN_SILENCE_MS,
    SessionFactory,
    _farewell_config,
    _silence_window_config,
)
from .streaming_runtime import StreamingVoiceSession
from .webrtc_support import probe_webrtc_support

# Concurrency ceiling for live WebRTC sessions (TASK-WEB-024). All sessions share one
# asyncio loop on a `ThreadingHTTPServer`, and the pilot LB VMs are 1 vCPU, so unbounded
# sessions are a latency + stability risk. New offers beyond the cap are refused with a
# clear 503 (backpressure) instead of degrading every live call. Env-tunable per host.
DEFAULT_MAX_WEBRTC_SESSIONS = 8
MAX_WEBRTC_SESSIONS_ENV_VAR = "VOICE_MAX_WEBRTC_SESSIONS"

# Metric/event names for the concurrency ceiling (TASK-WEB-024) — exported via OTLP as
# root-span attributes/events (see voice_common/otel_export) so the pilot can chart the
# active-session gauge and count refusals per host.
ACTIVE_SESSIONS_METRIC = "voice.webrtc.active_sessions"
SESSION_REJECTED_EVENT = "voice.webrtc.session_rejected"
REASON_CAPACITY = "capacity"

# End-of-call reasons emitted on the `voice.call_end` telemetry event (TASK-WEB-010).
END_OF_CALL_EVENT = "voice.call_end"
REASON_CUSTOMER_FAREWELL = "customer_farewell"
REASON_CLIENT_STOP = "client_stop"
REASON_CLIENT_DROP = "client_drop"

def _max_sessions_config() -> int:
    """Resolve the live WebRTC session cap (TASK-WEB-024).

    `VOICE_MAX_WEBRTC_SESSIONS` overrides the code default; a non-numeric or non-positive
    value falls back to `DEFAULT_MAX_WEBRTC_SESSIONS` rather than disabling the ceiling
    (an unbounded runtime on a 1 vCPU VM is the failure mode we are closing).
    """
    raw = os.environ.get(MAX_WEBRTC_SESSIONS_ENV_VAR)
    if raw is None:
        return DEFAULT_MAX_WEBRTC_SESSIONS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_WEBRTC_SESSIONS
    return value if value > 0 else DEFAULT_MAX_WEBRTC_SESSIONS


@dataclass
class _Session:
    connection: Any
    session: StreamingVoiceSession
    envelope: ChannelEnvelope
    telemetry: TelemetryRecorder
    task: Any = None
    # The farewell processor for this session (TASK-WEB-010), or None when the feature
    # is disabled / the batch path is used. Wired to the teardown callback post-build.
    farewell: Any = None
    # The end-of-call reason once recorded, so it is emitted exactly once (a bot farewell
    # must not be overwritten by the later `closed` event that its own disconnect fires).
    end_reason: str | None = None


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
    # Additive OTLP export (TASK-OBS-001): no-op unless OTEL_EXPORTER_OTLP_ENDPOINT /
    # VOICE_OTEL_EXPORT is set; never raises, so the stderr evidence above is authoritative.
    export_recorder(telemetry)


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
        max_sessions: int | None = None,
    ) -> None:
        support = probe_webrtc_support()
        if not support.available:
            raise RuntimeError(
                f"WebRTC runtime unavailable ({support.missing}). {support.install_hint}"
            )
        self._loop = loop
        self._ice_servers = ice_servers or []
        self._telemetry_factory = telemetry_factory
        self._log = log
        # Session assembly is transport-agnostic (TASK-WEB-027, ADR-0043): the factory
        # builds the StreamingVoiceSession (STT/TTS/farewell/egress + streaming vs batch)
        # for any transport. WebRTC only builds its own transport (see `_build_transport`)
        # and delegates the rest; the WebSocket path (TASK-WEB-028) and the future Genesys
        # adapter reuse the same factory. Provider selection (incl. per-language, US-042)
        # now lives in the factory.
        self._factory = SessionFactory(
            ingress=ingress,
            egress=egress,
            backend=backend,
            streaming_provider=streaming_provider,
            streaming_tts_provider=streaming_tts_provider,
            streaming_providers_by_language=streaming_providers_by_language,
            streaming_tts_providers_by_language=streaming_tts_providers_by_language,
        )
        self._sessions: dict[str, _Session] = {}
        # Concurrency ceiling (TASK-WEB-024): refuse new offers past this many live sessions.
        self._max_sessions = max_sessions if max_sessions is not None else _max_sessions_config()
        # Slots reserved by offers mid-negotiation (before they land in `_sessions`). All
        # negotiation runs on one asyncio loop, so incrementing this synchronously (no await
        # in between) reserves a slot atomically and stops concurrent offers from racing past
        # the cap while they `await connection.initialize(...)`.
        self._pending = 0

    @property
    def max_sessions(self) -> int:
        return self._max_sessions

    def active_sessions(self) -> int:
        """Number of live WebRTC sessions (the active-session gauge value)."""
        return len(self._sessions)

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

        # Backpressure (TASK-WEB-024): refuse before touching the WebRTC stack so a
        # rejection never allocates a connection. Counts live sessions + those still
        # negotiating (`_pending`) so concurrent offers cannot race past the cap. Checked
        # here (not on renegotiation) so in-call SDP updates are always honoured.
        active = len(self._sessions) + self._pending
        if active >= self._max_sessions:
            self._reject_session(active)
            raise SessionCapacityError(active, self._max_sessions)
        self._pending += 1  # reserve the slot for the length of this negotiation
        try:
            from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

            connection = SmallWebRTCConnection(ice_servers=self._ice_servers)
            await connection.initialize(sdp=body["sdp"], type=body["type"])
            # US-042: the UI-selected language rides on the offer body and is carried by the
            # session envelope -> forces the backend answer language and selects the voice.
            envelope = ChannelEnvelope.for_web_turn(language=body.get("language"))
            telemetry = self._telemetry_factory()
            transport = self._build_transport(connection)
            session, farewell = self._factory.build_session(transport, envelope, telemetry)
            record = _Session(connection, session, envelope, telemetry, farewell=farewell)
            self._register_cleanup(connection)
            self._sessions[connection.pc_id] = record
            # Active-session gauge on accept (count includes the new session, TASK-WEB-024).
            self._emit_active_gauge(telemetry, outcome="accepted")
            self._wire_farewell(record)
            answer = self._answer_payload(connection.get_answer(), envelope)
            record.task = asyncio.ensure_future(session.run())
            return answer
        finally:
            # Release the reservation once the session is registered (or the offer failed).
            self._pending -= 1

    def _emit_active_gauge(self, telemetry: TelemetryRecorder, *, outcome: str) -> None:
        """Record the active-session gauge (TASK-WEB-024) onto a call's recorder so the
        sample is dumped + OTLP-exported with the call. `outcome` labels the transition
        (accepted / closed / rejected) so the pilot can chart concurrency and refusals."""
        telemetry.metric(
            ACTIVE_SESSIONS_METRIC,
            float(len(self._sessions)),
            outcome=outcome,
            max_sessions=self._max_sessions,
        )

    def _reject_session(self, active: int) -> None:
        """Emit the refusal evidence for a capacity-rejected offer (TASK-WEB-024).

        A rejected offer never gets a session recorder, so a fresh one carries the event +
        gauge and is logged immediately (the client gets a 503 from the HTTP layer). The
        event reports the effective count that hit the cap (live + negotiating); the gauge
        stays the live-session count."""
        telemetry = self._telemetry_factory()
        telemetry.record(
            SESSION_REJECTED_EVENT,
            reason=REASON_CAPACITY,
            active_sessions=active,
            max_sessions=self._max_sessions,
        )
        self._emit_active_gauge(telemetry, outcome="rejected")
        self._log(telemetry)

    def _wire_farewell(self, record: _Session) -> None:
        """Give the farewell processor a teardown callback now that its session/connection
        exist: on a confirmed farewell it records the end-of-call reason then reuses the
        TASK-WEB-008 drain path to speak the closing and end the call."""
        if record.farewell is None:
            return

        async def _end_call(signal: str) -> None:
            await self._on_farewell(record, signal)

        record.farewell.set_end_call(_end_call)

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
            await self._drain_and_discard(conn.pc_id, reason=REASON_CLIENT_STOP)

        @connection.event_handler("disconnected")
        async def _on_disconnected(conn) -> None:  # noqa: ANN001 - pipecat callback signature
            await self._drain_and_discard(conn.pc_id, reason=REASON_CLIENT_DROP)

    async def _drain_and_discard(self, pc_id: str, reason: str = REASON_CLIENT_STOP) -> None:
        """On call end/drop: record the end-of-call reason, flush a trailing partial
        utterance (TASK-WEB-008), then discard. A bot-initiated farewell has already
        recorded `customer_farewell`, so `_record_end_of_call` leaves it untouched here.
        Draining is best-effort; teardown always proceeds.
        """
        record = self._sessions.get(pc_id)
        if record is not None:
            self._record_end_of_call(record, reason=reason)
            await self._drain(record)
        self._discard(pc_id)

    def _record_end_of_call(self, record: _Session, *, reason: str, signal: str | None = None) -> None:
        """Emit the end-of-call reason once under the call correlation id (TASK-WEB-010):
        `customer_farewell` (bot ended the call) vs `client_stop`/`client_drop` (manual
        hangup / abrupt drop). Pilot review reads this to attribute every call ending."""
        if record.end_reason is not None:
            return
        record.end_reason = reason
        attributes = {"correlation_id": record.envelope.correlation_id, "reason": reason}
        if signal is not None:
            attributes["signal"] = signal
        record.telemetry.record(END_OF_CALL_EVENT, **attributes)

    async def _on_farewell(self, record: _Session, signal: str) -> None:
        """Confirmed farewell: record the reason and schedule the graceful teardown off
        the pipeline task (we must not await our own run() task from inside it)."""
        import asyncio

        self._record_end_of_call(record, reason=REASON_CUSTOMER_FAREWELL, signal=signal)
        asyncio.ensure_future(self._farewell_teardown(record))

    async def _farewell_teardown(self, record: _Session, timeout: float = 10.0) -> None:
        """Let the closing message drain (TASK-WEB-008 path), then disconnect. Disconnect
        fires `closed` -> `_drain_and_discard` -> `_discard`, which logs telemetry once
        (the reason is already recorded). Bounded so a stuck transport never hangs."""
        import asyncio

        try:
            await record.session.drain()  # queue EndFrame; the closing plays, then run() ends
            if record.task is not None:
                await asyncio.wait_for(asyncio.shield(record.task), timeout=timeout)
        except Exception:  # noqa: BLE001 - teardown is best-effort, never blocks/raises
            pass
        try:
            await record.connection.disconnect()
        except Exception:  # noqa: BLE001 - connection may already be closing
            pass

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
            # Active-session gauge after removal (count reflects the freed slot, TASK-WEB-024).
            self._emit_active_gauge(record.telemetry, outcome="closed")
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
