"""Genesys Audio Connector transport adapter on the single async server (TASK-WEB-041).

The Genesys-facing counterpart of the browser `GET /ws` handler (`websocket_app.py`):
an AudioHook-shaped `wss://` endpoint (`GET /genesys/audiohook`) mounted on the SAME
ADR-0047 single async HTTP+WebSocket server. Each accepted connection is one
bidirectional audio stream per session, built through the unchanged ADR-0043
`SessionFactory` (STT -> backend answer -> TTS), so the shared session core is untouched
and no business logic lives here (ADR-0001 boundary holds).

What this adapter owns (the transport boundary):
- PCMU/L16 <-> PCM16/16 kHz codec, inside `GenesysAudioConnectorSerializer` (prefer L16).
- A concurrency ceiling (default 3, the DEC-014 pilot target) with WS 1013 backpressure.
- A graceful **15-minute call cap** with a HARD duration bound: at the cap the session is
  *drained* (a trailing partial is finalized, the answer is spoken) then ended cleanly so
  Architect resumes and routes to the advisor queue — never a silent mid-call cut (R2). If
  the drain wedges (a stuck STT/TTS provider), it is force-stopped after a bounded grace so
  the concurrency slot + WS are ALWAYS freed at cap+grace (review Major #1).
- An Origin allowlist (anti-CSWSH) mirroring `/ws`; combined with the default-off posture
  (`--genesys off`) this keeps the endpoint closed until AudioHook signature/HMAC
  verification lands under TASK-INFRA-012 (review Major #2 / ADR-0049).
- Per-channel OpenTelemetry: session/gauge/cap events labelled `genesys_audio_connector`,
  plus a deterministic `traceparent` derived from the Genesys `conversationId` so the
  Genesys leg + runtime + backend land in one trace (per-leg transcode spans come from
  the serializer). Barge-in/EOT ownership on this path is TASK-WEB-042.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiohttp import web
from pipecat.utils.security.allowed_origins import is_origin_allowed

from voice_common.telemetry import TelemetryRecorder

from .envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL, ChannelEnvelope
from .genesys_cap import DrainOnce, cancel_cap, schedule_cap, wire_disconnect_drain
from .genesys_config import (
    CLIENT_DISCONNECTED_EVENT,
    DEFAULT_CAP_DRAIN_GRACE_S,
    DEFAULT_MAX_GENESYS_SESSIONS,
    DEFAULT_MAX_SESSION_S,
    emit_gauge,
    genesys_codec_config,
    record_started,
    reject,
)
from .genesys_framing import GenesysAudioConnectorSerializer
from .genesys_timing import genesys_log_telemetry
from .session_factory import SessionFactory
from .websocket_app import (
    DEFAULT_SAMPLE_RATE,
    AiohttpWebsocketParams,
    AiohttpWebsocketTransport,
    _ActiveSessions,
    _safe_stop,
)

_logger = logging.getLogger(__name__)

GENESYS_ROUTE = "/genesys/audiohook"
# WS close code for an Origin the allowlist refuses (anti-CSWSH), matching `/ws`.
WS_POLICY_VIOLATION = 1008


def _conversation_id(request: web.Request) -> str | None:
    """The Genesys conversationId from the AudioHook handshake (query, best-effort)."""
    query = request.query
    return query.get("conversationId") or query.get("conversation_id") or None


def make_genesys_handler(
    factory: SessionFactory,
    *,
    max_sessions: int = DEFAULT_MAX_GENESYS_SESSIONS,
    wire_codec: str | None = None,
    max_session_s: float = DEFAULT_MAX_SESSION_S,
    cap_drain_grace_s: float = DEFAULT_CAP_DRAIN_GRACE_S,
    allowed_origins: list[str] | None = None,
    default_language: str | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    telemetry_factory: Callable[[], TelemetryRecorder] = TelemetryRecorder,
    log: Callable[[TelemetryRecorder], None] = genesys_log_telemetry,
) -> Callable[[web.Request], Awaitable[web.WebSocketResponse]]:
    """Build the `GET /genesys/audiohook` handler: one session per connection, N concurrent."""
    active = _ActiveSessions()
    ceiling = max_sessions if max_sessions > 0 else DEFAULT_MAX_GENESYS_SESSIONS
    codec = wire_codec or genesys_codec_config()

    async def handler(request: web.Request) -> web.WebSocketResponse:
        websocket = web.WebSocketResponse()
        await websocket.prepare(request)
        if allowed_origins and not is_origin_allowed(
            request.headers.get("Origin", ""), allowed_origins
        ):
            await websocket.close(code=WS_POLICY_VIOLATION)
            return websocket
        if active.count >= ceiling:
            await reject(websocket, active, ceiling, telemetry_factory, log)
            return websocket
        await _serve_genesys_connection(
            websocket,
            request,
            factory=factory,
            active=active,
            max_sessions=ceiling,
            wire_codec=codec,
            max_session_s=max_session_s,
            cap_drain_grace_s=cap_drain_grace_s,
            default_language=default_language,
            sample_rate=sample_rate,
            telemetry_factory=telemetry_factory,
            log=log,
        )
        return websocket

    return handler


def _build_serializer(
    wire_codec: str, sample_rate: int, telemetry: TelemetryRecorder, cid: str
) -> GenesysAudioConnectorSerializer:
    params = GenesysAudioConnectorSerializer.InputParams(
        sample_rate=sample_rate, wire_codec=wire_codec
    )
    return GenesysAudioConnectorSerializer(params, telemetry=telemetry, correlation_id=cid)


def _build_transport(
    websocket: web.WebSocketResponse, serializer: GenesysAudioConnectorSerializer, sample_rate: int
) -> AiohttpWebsocketTransport:
    params = AiohttpWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_sample_rate=sample_rate,
        audio_out_sample_rate=sample_rate,
        add_wav_header=False,
        serializer=serializer,
    )
    return AiohttpWebsocketTransport(websocket, params)


async def _serve_genesys_connection(
    websocket: web.WebSocketResponse,
    request: web.Request,
    *,
    factory: SessionFactory,
    active: _ActiveSessions,
    max_sessions: int,
    wire_codec: str,
    max_session_s: float,
    cap_drain_grace_s: float,
    default_language: str | None,
    sample_rate: int,
    telemetry_factory: Callable[[], TelemetryRecorder],
    log: Callable[[TelemetryRecorder], None],
) -> None:
    """Own one Genesys audio session end to end (build -> run -> cap/teardown -> dump)."""
    telemetry = telemetry_factory()
    envelope = ChannelEnvelope.for_genesys_turn(
        conversation_id=_conversation_id(request), language=default_language
    )
    cid = envelope.correlation_id
    serializer = _build_serializer(wire_codec, sample_rate, telemetry, cid)
    transport = _build_transport(websocket, serializer, sample_rate)
    session, _ = factory.build_session(transport, envelope, telemetry)
    drain = DrainOnce()
    wire_disconnect_drain(transport, session, drain)
    active.count += 1
    record_started(telemetry, cid, envelope, wire_codec, active.count, max_sessions)
    drain.cap = schedule_cap(session, drain, telemetry, cid, max_session_s, cap_drain_grace_s)
    await _run_and_teardown(session, telemetry, cid, active, max_sessions, drain.cap, log)


async def _run_and_teardown(
    session: Any,
    telemetry: TelemetryRecorder,
    cid: str,
    active: _ActiveSessions,
    max_sessions: int,
    cap: asyncio.Task | None,
    log: Callable[[TelemetryRecorder], None],
) -> None:
    try:
        await session.run()
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - one failed turn must not raise out of the handler
        _logger.error("genesys session run failed", exc_info=True)
    finally:
        cancel_cap(cap)
        active.count = max(0, active.count - 1)
        telemetry.record(
            CLIENT_DISCONNECTED_EVENT, correlation_id=cid, channel=GENESYS_AUDIO_CONNECTOR_CHANNEL
        )
        emit_gauge(telemetry, cid, active.count, max_sessions, "closed")
        log(telemetry)
        await _safe_stop(session)
