"""Config resolvers + telemetry emitters for the Genesys Audio Connector adapter.

Extracted from `genesys_app.py` (TASK-WEB-041 review) so the handler module stays within
the module/class size budget. This module owns the transport-boundary constants (env-var
names, defaults, OTel event/metric vocabulary), the env config resolvers (concurrency
ceiling, 15-min cap, cap-drain grace, wire codec, Origin allowlist) and the shared
telemetry emitters (active-session gauge, session `started`/`connected`, capacity refusal).
No transport/session logic lives here — that stays in `genesys_app.py`.
"""

from __future__ import annotations

import os
from typing import Callable

from aiohttp import web

from voice_common.telemetry import TelemetryRecorder
from voice_common.trace_context import derive_traceparent

from .envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL, ChannelEnvelope
from .websocket_app import WS_TRY_AGAIN_LATER, _ActiveSessions

# DEC-014 pilot target = 3 concurrent Genesys sessions (checked vs premium <=5 / 1 vCPU).
DEFAULT_MAX_GENESYS_SESSIONS = 3
# AudioHook's documented per-session cap; graceful end at the boundary (R2).
DEFAULT_MAX_SESSION_S = 900.0
# Hard bound on the graceful cap drain: if drain() wedges (a stuck STT/TTS provider), the
# session is force-stopped after this grace so the concurrency slot + WS are ALWAYS freed at
# cap+grace and never held indefinitely (review Major #1).
DEFAULT_CAP_DRAIN_GRACE_S = 5.0

MAX_SESSIONS_ENV_VAR = "VOICE_GENESYS_MAX_SESSIONS"
MAX_SESSION_S_ENV_VAR = "VOICE_GENESYS_MAX_SESSION_S"
CAP_DRAIN_GRACE_MS_ENV_VAR = "VOICE_GENESYS_CAP_DRAIN_GRACE_MS"
CODEC_ENV_VAR = "VOICE_GENESYS_CODEC"
ALLOWED_ORIGINS_ENV_VAR = "VOICE_GENESYS_ALLOWED_ORIGINS"

SESSION_STARTED_EVENT = "voice.genesys.session_started"
CLIENT_CONNECTED_EVENT = "voice.genesys.client_connected"
CLIENT_DISCONNECTED_EVENT = "voice.genesys.client_disconnected"
ACTIVE_SESSIONS_METRIC = "voice.genesys.active_sessions"
# Backpressure counter (TASK-WEB-043): every WS 1013 capacity refusal emits one sample so
# refusals are aggregatable per channel by the OTel exporter / latency report, not only
# visible as a one-off event.
SESSION_REJECTED_METRIC = "voice.genesys.session_rejected"
SESSION_REJECTED_EVENT = "voice.genesys.session_rejected"
SESSION_CAP_EVENT = "voice.genesys.session_cap"
SESSION_CAP_FORCED_EVENT = "voice.genesys.session_cap_forced"
REASON_CAPACITY = "capacity"
REASON_CAP_REACHED = "cap_reached"
REASON_CAP_DRAIN_TIMEOUT = "cap_drain_timeout"

# End-of-call telemetry vocabulary for the Genesys path (TASK-WEB-042). Same event name +
# reason values as the WebRTC/WS path (webrtc_signaling `voice.call_end`) so call endings
# aggregate across channels; always emitted with channel=genesys_audio_connector. The cap path
# reuses REASON_CAP_REACHED above. The AudioHook transport surfaces a single "peer went away"
# signal (no clean stop-vs-drop split like WebRTC), so it records one honest disconnect reason.
CALL_END_EVENT = "voice.call_end"
REASON_CUSTOMER_FAREWELL = "customer_farewell"
REASON_CLIENT_DISCONNECT = "client_disconnect"


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


def genesys_cap_drain_grace_s_config() -> float:
    """Resolve the cap-drain grace in seconds (default 5s; env is ms; garbage/<=0 -> default)."""
    raw = os.environ.get(CAP_DRAIN_GRACE_MS_ENV_VAR)
    if raw is None:
        return DEFAULT_CAP_DRAIN_GRACE_S
    try:
        ms = float(raw)
    except ValueError:
        return DEFAULT_CAP_DRAIN_GRACE_S
    return ms / 1000.0 if ms > 0 else DEFAULT_CAP_DRAIN_GRACE_S


def genesys_codec_config() -> str:
    """Resolve the Genesys wire codec (default L16; unknown value falls back to default)."""
    from . import genesys_codec

    raw = (os.environ.get(CODEC_ENV_VAR) or "").strip().upper()
    return raw if raw in genesys_codec.SUPPORTED_CODECS else genesys_codec.DEFAULT_CODEC


def genesys_allowed_origins_config() -> list[str] | None:
    """Resolve the Origin allowlist (anti-CSWSH). Empty/unset -> None (allow all: dev/loopback).

    The AudioHook signature/HMAC verification (TASK-INFRA-012) is the primary connection
    auth and is enforced before the WS upgrade; this Origin allowlist is a second,
    reversible defense-in-depth guard that refuses disallowed Origins. The endpoint also
    stays default-off (VOICE_GENESYS).
    """
    raw = os.environ.get(ALLOWED_ORIGINS_ENV_VAR) or ""
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or None


def emit_gauge(
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


def record_started(
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
    emit_gauge(telemetry, cid, active_count, max_sessions, "accepted")


async def reject(
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
    telemetry.metric(
        SESSION_REJECTED_METRIC,
        1.0,
        correlation_id=cid,
        channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
        reason=REASON_CAPACITY,
        max_sessions=max_sessions,
    )
    emit_gauge(telemetry, cid, active.count, max_sessions, "rejected")
    log(telemetry)
    await websocket.close(code=WS_TRY_AGAIN_LATER)


def genesys_conversation_id(request: web.Request) -> str | None:
    """The Genesys conversationId from the AudioHook handshake (query, best-effort).

    Extracted from `genesys_app.py` (module-budget split) so the handler module stays lean;
    the id becomes the turn correlation id + the deterministic one-trace `traceparent`.
    """
    query = request.query
    return query.get("conversationId") or query.get("conversation_id") or None


def _positive_int_env(env_var: str, default: int) -> int:
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default
