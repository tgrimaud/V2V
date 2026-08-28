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
- A graceful **15-minute call cap**: at the cap the session is *drained* (a trailing
  partial is finalized, the answer is spoken) then ended cleanly so Architect resumes and
  routes to the advisor queue — never a silent mid-call cut (R2). The resume/callback
  policy and the endpoint-down fail-safe are TASK-WEB-044 + TASK-INFRA-012.
- Per-channel OpenTelemetry: session/gauge/cap events labelled `genesys_audio_connector`,
  plus a deterministic `traceparent` derived from the Genesys `conversationId` so the
  Genesys leg + runtime + backend land in one trace (per-leg transcode spans come from
  the serializer). Barge-in/EOT ownership on this path is TASK-WEB-042.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

from aiohttp import web

from voice_common.telemetry import TelemetryRecorder
from voice_common.trace_context import derive_traceparent

from .envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL, ChannelEnvelope
from .genesys_framing import GenesysAudioConnectorSerializer
from .session_factory import SessionFactory
from .session_telemetry import log_telemetry
from .websocket_app import (
    DEFAULT_SAMPLE_RATE,
    WS_TRY_AGAIN_LATER,
    AiohttpWebsocketParams,
    AiohttpWebsocketTransport,
    _ActiveSessions,
    _safe_stop,
    _wire_disconnect_drain,
)

_logger = logging.getLogger(__name__)

GENESYS_ROUTE = "/genesys/audiohook"
# DEC-014 pilot target = 3 concurrent Genesys sessions (checked vs premium <=5 / 1 vCPU).
DEFAULT_MAX_GENESYS_SESSIONS = 3
# AudioHook's documented per-session cap; graceful end at the boundary (R2).
DEFAULT_MAX_SESSION_S = 900.0
MAX_SESSIONS_ENV_VAR = "VOICE_GENESYS_MAX_SESSIONS"
MAX_SESSION_S_ENV_VAR = "VOICE_GENESYS_MAX_SESSION_S"
CODEC_ENV_VAR = "VOICE_GENESYS_CODEC"

SESSION_STARTED_EVENT = "voice.genesys.session_started"
CLIENT_CONNECTED_EVENT = "voice.genesys.client_connected"
CLIENT_DISCONNECTED_EVENT = "voice.genesys.client_disconnected"
ACTIVE_SESSIONS_METRIC = "voice.genesys.active_sessions"
SESSION_REJECTED_EVENT = "voice.genesys.session_rejected"
SESSION_CAP_EVENT = "voice.genesys.session_cap"
REASON_CAPACITY = "capacity"
REASON_CAP_REACHED = "cap_reached"


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
    default_language: str | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    telemetry_factory: Callable[[], TelemetryRecorder] = TelemetryRecorder,
    log: Callable[[TelemetryRecorder], None] = log_telemetry,
) -> Callable[[web.Request], Awaitable[web.WebSocketResponse]]:
    """Build the `GET /genesys/audiohook` handler: one session per connection, N concurrent."""
    active = _ActiveSessions()
    ceiling = max_sessions if max_sessions > 0 else DEFAULT_MAX_GENESYS_SESSIONS
    codec = wire_codec or genesys_codec_config()

    async def handler(request: web.Request) -> web.WebSocketResponse:
        websocket = web.WebSocketResponse()
        await websocket.prepare(request)
        if active.count >= ceiling:
            await _reject(websocket, active, ceiling, telemetry_factory, log)
            return websocket
        await _serve_genesys_connection(
            websocket,
            request,
            factory=factory,
            active=active,
            max_sessions=ceiling,
            wire_codec=codec,
            max_session_s=max_session_s,
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
    _wire_disconnect_drain(transport, session)
    active.count += 1
    _record_started(telemetry, cid, envelope, wire_codec, active.count, max_sessions)
    cap = _schedule_cap(session, telemetry, cid, max_session_s)
    await _run_and_teardown(session, telemetry, cid, active, max_sessions, cap, log)


def _record_started(
    telemetry: TelemetryRecorder,
    cid: str,
    envelope: ChannelEnvelope,
    wire_codec: str,
    active_count: int,
    max_sessions: int,
) -> None:
    telemetry.record(
        SESSION_STARTED_EVENT,
        correlation_id=cid,
        channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
        wire_codec=wire_codec,
        traceparent=derive_traceparent(cid),
        effective_language=envelope.language or "auto",
    )
    telemetry.record(
        CLIENT_CONNECTED_EVENT,
        correlation_id=cid,
        channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
        conversation_id=envelope.conversation_id,
    )
    _emit_gauge(telemetry, cid, active_count, max_sessions, "accepted")


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
        _cancel_cap(cap)
        active.count = max(0, active.count - 1)
        telemetry.record(
            CLIENT_DISCONNECTED_EVENT, correlation_id=cid, channel=GENESYS_AUDIO_CONNECTOR_CHANNEL
        )
        _emit_gauge(telemetry, cid, active.count, max_sessions, "closed")
        log(telemetry)
        await _safe_stop(session)


def _schedule_cap(
    session: Any, telemetry: TelemetryRecorder, cid: str, max_session_s: float
) -> asyncio.Task | None:
    """Arm the graceful 15-min cap timer, or None when disabled (max_session_s <= 0)."""
    if max_session_s <= 0:
        return None
    return asyncio.ensure_future(_cap_after(session, telemetry, cid, max_session_s))


async def _cap_after(session: Any, telemetry: TelemetryRecorder, cid: str, delay: float) -> None:
    """At the cap, record it and drain the session gracefully (never a silent cut)."""
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    telemetry.record(
        SESSION_CAP_EVENT,
        correlation_id=cid,
        channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
        reason=REASON_CAP_REACHED,
        max_session_s=delay,
    )
    try:
        await session.drain()
    except Exception:  # noqa: BLE001 - drain is best-effort; run() still returns on teardown
        _logger.debug("genesys cap drain failed", exc_info=True)


def _cancel_cap(cap: asyncio.Task | None) -> None:
    if cap is not None and not cap.done():
        cap.cancel()


async def _reject(
    websocket: web.WebSocketResponse,
    active: _ActiveSessions,
    max_sessions: int,
    telemetry_factory: Callable[[], TelemetryRecorder],
    log: Callable[[TelemetryRecorder], None],
) -> None:
    """Refuse an over-capacity connection with WS 1013 and record the refusal evidence."""
    telemetry = telemetry_factory()
    cid = ChannelEnvelope.for_genesys_turn().correlation_id
    telemetry.record(
        SESSION_REJECTED_EVENT,
        correlation_id=cid,
        channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
        reason=REASON_CAPACITY,
        active_sessions=active.count,
        max_sessions=max_sessions,
    )
    _emit_gauge(telemetry, cid, active.count, max_sessions, "rejected")
    log(telemetry)
    await websocket.close(code=WS_TRY_AGAIN_LATER)


def _emit_gauge(
    telemetry: TelemetryRecorder, cid: str, active_count: int, max_sessions: int, outcome: str
) -> None:
    telemetry.metric(
        ACTIVE_SESSIONS_METRIC,
        float(active_count),
        correlation_id=cid,
        channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
        outcome=outcome,
        max_sessions=max_sessions,
    )


def genesys_max_sessions_config() -> int:
    """Resolve the Genesys concurrency ceiling (DEC-014 target 3; env override)."""
    return _positive_int_env(MAX_SESSIONS_ENV_VAR, DEFAULT_MAX_GENESYS_SESSIONS)


def genesys_max_session_s_config() -> float:
    """Resolve the graceful call-cap seconds (default 900; <=0 disables; env override)."""
    raw = os.environ.get(MAX_SESSION_S_ENV_VAR)
    if raw is None:
        return DEFAULT_MAX_SESSION_S
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_MAX_SESSION_S


def genesys_codec_config() -> str:
    """Resolve the Genesys wire codec (default L16; unknown value falls back to default)."""
    from . import genesys_codec

    raw = (os.environ.get(CODEC_ENV_VAR) or "").strip().upper()
    return raw if raw in genesys_codec.SUPPORTED_CODECS else genesys_codec.DEFAULT_CODEC


def _positive_int_env(env_var: str, default: int) -> int:
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default
