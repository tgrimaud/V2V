"""Server-side signaling for the interim browser WebSocket voice path (TASK-WEB-028).

ADR-0043: the external browser path rides a `wss` connection (JSON control + binary
PCM16/16 kHz audio) instead of TURN. This service is the **thin transport adapter** that
WEB-026 (socle) + WEB-027 (session factory) were built for: it constructs the pipecat
`SingleClientWebsocketServerTransport` (no FastAPI) via `build_websocket_audio_transport`,
builds a `StreamingVoiceSession` through the shared `SessionFactory`, and runs it on the
shared background asyncio loop — exactly like `WebRtcSignalingService`, but over a socket
instead of an SDP negotiation.

Interim scope (deliberate, ADR-0043):
- **One call at a time.** The socle transport serves a single client; a second concurrent
  connection is rejected by pipecat with WebSocket close code **1013**, which the browser
  surfaces as a "try again shortly" message (TASK-WEB-028 AC#2). Rich capacity ceiling +
  per-slice spans + active-session gauge are TASK-WEB-030.
- **Language is fr-first.** Unlike the batch (`?language=` query per HTTP turn) and WebRTC
  (language in the SDP offer body) paths, the `wss` path has **no pre-media signaling step**
  to declare a language before the pipeline (and its fr/en provider selection) is built: the
  pipecat transport binds then accepts, and `ChannelEnvelope` is frozen. So the effective
  STT/TTS/answer language is the server default (`VOICE_WS_LANGUAGE`, None = backend
  auto-detect). The client's declared language (WS URL query + `open` control frame) is
  captured for telemetry/correlation; full dynamic per-call fr/en selection is deferred
  (candidate: a listener-per-language topology or a pre-media signaling hook) — OQ tracked
  and revisited with TASK-WEB-030.
"""

import os
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from voice_common.telemetry import TelemetryRecorder

from .async_loop import BackgroundEventLoop
from .envelope import ChannelEnvelope
from .session_factory import SessionFactory
from .session_telemetry import log_telemetry
from .websocket_framing import WebSocketAudioSerializer
from .websocket_support import (
    DEFAULT_SAMPLE_RATE,
    build_websocket_audio_transport,
    probe_websocket_support,
)

DEFAULT_WS_HOST = "0.0.0.0"
DEFAULT_WS_PORT = 8091
WS_HOST_ENV_VAR = "VOICE_WS_HOST"
WS_PORT_ENV_VAR = "VOICE_WS_PORT"
WS_LANGUAGE_ENV_VAR = "VOICE_WS_LANGUAGE"
WS_MAX_SESSIONS_ENV_VAR = "VOICE_MAX_WS_SESSIONS"
# The socle transport is single-client per listener, so the effective interim ceiling is 1.
# Kept env-tunable + stamped on the gauge for parity with the WebRTC ceiling (TASK-WEB-024);
# a value > 1 would need a listener-per-session topology (deferred, same OQ as the language
# selection — see the module docstring / ADR-0043).
DEFAULT_MAX_WS_SESSIONS = 1

# Telemetry names for the interim WS path (TASK-WEB-028 events + TASK-WEB-030 capacity).
SESSION_STARTED_EVENT = "voice.ws.session_started"
CLIENT_CONNECTED_EVENT = "voice.ws.client_connected"
CLIENT_DISCONNECTED_EVENT = "voice.ws.client_disconnected"
# Capacity ceiling (TASK-WEB-030), mirroring the WebRTC gauge/refusal shape so the pilot can
# chart active sessions + count refusals per host across both transports.
ACTIVE_SESSIONS_METRIC = "voice.ws.active_sessions"
SESSION_REJECTED_EVENT = "voice.ws.session_rejected"
REASON_SINGLE_CLIENT = "single_client_capacity"


class WebSocketSignalingService:
    """Owns the interim browser `wss` voice session on the shared background loop."""

    def __init__(
        self,
        *,
        factory: SessionFactory,
        loop: BackgroundEventLoop,
        host: str = DEFAULT_WS_HOST,
        port: int = DEFAULT_WS_PORT,
        default_language: str | None = None,
        allowed_origins: list[str] | None = None,
        max_sessions: int = DEFAULT_MAX_WS_SESSIONS,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        serializer_factory: Callable[[], WebSocketAudioSerializer] = WebSocketAudioSerializer,
        telemetry_factory: Callable[[], TelemetryRecorder] = TelemetryRecorder,
        log: Callable[[TelemetryRecorder], None] = log_telemetry,
        transport_builder: Callable[..., Any] = build_websocket_audio_transport,
    ) -> None:
        support = probe_websocket_support()
        if not support.available:
            raise RuntimeError(
                f"WebSocket runtime unavailable ({support.missing}). {support.install_hint}"
            )
        self._factory = factory
        self._loop = loop
        self._host = host
        self._port = port
        self._default_language = default_language
        self._allowed_origins = allowed_origins
        self._max_sessions = max_sessions if max_sessions > 0 else DEFAULT_MAX_WS_SESSIONS
        self._active = 0
        # Guards the per-call dump so a normal disconnect + a later shutdown do not double-dump.
        self._dumped = False
        self._sample_rate = sample_rate
        self._serializer_factory = serializer_factory
        self._telemetry_factory = telemetry_factory
        self._log = log
        self._transport_builder = transport_builder
        self._serializer: WebSocketAudioSerializer | None = None
        self._transport: Any = None
        self._session: Any = None
        self._envelope: ChannelEnvelope | None = None
        self._telemetry: TelemetryRecorder | None = None
        self._task: Any = None

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> str:
        """Build the transport + session and run it on the shared loop.

        Returns the call correlation id. The transport binds `host:port` and begins
        accepting one client when the pipeline `StartFrame` fires on the loop.
        """
        self._serializer = self._serializer_factory()
        self._transport = self._transport_builder(
            self._host,
            self._port,
            sample_rate=self._sample_rate,
            serializer=self._serializer,
            allowed_origins=self._allowed_origins,
            on_client_rejected=self._on_client_rejected,
        )
        self._telemetry = self._telemetry_factory()
        self._envelope = ChannelEnvelope.for_web_turn(language=self._default_language)
        self._session, _ = self._factory.build_session(
            self._transport, self._envelope, self._telemetry
        )
        self._wire_events()
        self._telemetry.record(
            SESSION_STARTED_EVENT,
            correlation_id=self._envelope.correlation_id,
            effective_language=self._envelope.language or "auto",
            host=self._host,
            port=self._port,
        )
        self._task = self._loop.spawn(self._session.run())
        return self._envelope.correlation_id

    def _wire_events(self) -> None:
        transport = self._transport

        @transport.event_handler("on_client_connected")
        async def _connected(_transport, websocket) -> None:  # noqa: ANN001 - pipecat callback
            self._on_client_connected(websocket)

        @transport.event_handler("on_client_disconnected")
        async def _disconnected(_transport, websocket) -> None:  # noqa: ANN001 - pipecat callback
            self._on_client_disconnected(websocket)

    def _on_client_connected(self, websocket) -> None:
        """Record the client-connected evidence, incl. the language the client declared
        on the WS URL (the `open` control frame is captured by the serializer). Effective
        language stays the server default in the interim (see the module docstring)."""
        declared = self._declared_language(websocket)
        self._active += 1
        self._dumped = False
        self._telemetry.record(
            CLIENT_CONNECTED_EVENT,
            correlation_id=self._envelope.correlation_id,
            declared_language=declared or "",
            effective_language=self._envelope.language or "auto",
        )
        self._emit_active_gauge(outcome="accepted")

    def _on_client_disconnected(self, websocket) -> None:
        self._active = max(0, self._active - 1)
        self._telemetry.record(
            CLIENT_DISCONNECTED_EVENT,
            correlation_id=self._envelope.correlation_id,
        )
        self._emit_active_gauge(outcome="closed")
        # Per-call evidence dump (TASK-WEB-030): a streaming call has no per-turn HTTP
        # response, so dump the canonical per-slice timing at call end (like WebRTC's
        # _discard), not only at server shutdown.
        self._dump_once()

    async def _on_client_rejected(self, websocket) -> None:
        """Fired by the socle when an extra concurrent client is refused (WS 1013).

        Async to match the transport callback signature; only records telemetry so it never
        blocks the refusal. The active gauge is emitted with `outcome=rejected` and the
        rejected client is counted, mirroring the WebRTC ceiling (TASK-WEB-024)."""
        self._telemetry.record(
            SESSION_REJECTED_EVENT,
            correlation_id=self._envelope.correlation_id,
            reason=REASON_SINGLE_CLIENT,
            active_sessions=self._active,
            max_sessions=self._max_sessions,
        )
        self._emit_active_gauge(outcome="rejected")

    def _emit_active_gauge(self, *, outcome: str) -> None:
        self._telemetry.metric(
            ACTIVE_SESSIONS_METRIC,
            float(self._active),
            correlation_id=self._envelope.correlation_id,
            outcome=outcome,
            max_sessions=self._max_sessions,
        )

    def _dump_once(self) -> None:
        if self._telemetry is not None and not self._dumped:
            self._dumped = True
            self._log(self._telemetry)

    @staticmethod
    def _declared_language(websocket) -> str | None:
        """Read `?language=` from the WS handshake path (best-effort, never raises)."""
        request = getattr(websocket, "request", None)
        path = getattr(request, "path", "") or ""
        try:
            values = parse_qs(urlparse(path).query).get("language")
        except Exception:  # noqa: BLE001 - a malformed path must never break connect
            return None
        return values[0] if values else None

    def close(self) -> None:
        """Stop the session/transport on the loop and dump the call telemetry once.

        The dump is idempotent (`_dump_once`): a client disconnect already dumped this
        call's evidence, so a shutdown after a clean disconnect does not double-dump; a
        shutdown *mid-call* (no disconnect) still dumps here."""
        if self._session is not None:
            try:
                self._loop.run(self._teardown(), timeout=10)
            except Exception:  # noqa: BLE001 - best-effort teardown on shutdown
                pass
        self._dump_once()

    async def _teardown(self) -> None:
        await self._session.stop()


def ws_host_config() -> str:
    return os.environ.get(WS_HOST_ENV_VAR) or DEFAULT_WS_HOST


def ws_port_config() -> int:
    """Resolve the WS listener port; a non-numeric/non-positive value keeps the default."""
    raw = os.environ.get(WS_PORT_ENV_VAR)
    if raw is None:
        return DEFAULT_WS_PORT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_WS_PORT
    return value if value > 0 else DEFAULT_WS_PORT


def ws_language_config() -> str | None:
    """Server-default language for the interim WS path (None = backend auto-detect)."""
    raw = os.environ.get(WS_LANGUAGE_ENV_VAR)
    return raw.strip().lower() if raw and raw.strip() else None


def ws_max_sessions_config() -> int:
    """Resolve the WS session ceiling (TASK-WEB-030).

    `VOICE_MAX_WS_SESSIONS` overrides the default; a non-numeric/non-positive value falls
    back to `DEFAULT_MAX_WS_SESSIONS` (1). The socle transport is single-client per listener,
    so this is primarily the value stamped on the active-session gauge for cross-transport
    parity — a real ceiling > 1 needs a listener-per-session topology (deferred)."""
    raw = os.environ.get(WS_MAX_SESSIONS_ENV_VAR)
    if raw is None:
        return DEFAULT_MAX_WS_SESSIONS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_WS_SESSIONS
    return value if value > 0 else DEFAULT_MAX_WS_SESSIONS
