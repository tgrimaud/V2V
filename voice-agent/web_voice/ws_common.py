"""Transport-neutral WebSocket constants + config shared by the live `/ws` path.

Extracted from the (retired) interim `websocket_signaling.py` by TASK-WEB-048 / ADR-0053:
these telemetry event/metric names, the session-ceiling env var and the server-default
language config are **not** interim-specific — the shipped aiohttp `/ws` transport
(`websocket_app.py`) and the runtime wiring (`server.py`) consume them. Keeping them in a
neutral module lets the interim single-client transport be removed without touching the
kept path, and preserves the exact names/values (no telemetry or behaviour change).
"""

import os

# Session-ceiling env var (shared by the aiohttp `/ws` capacity gauge, US-036/TASK-WEB-030).
WS_MAX_SESSIONS_ENV_VAR = "VOICE_MAX_WS_SESSIONS"
# Server-default answer language for the WS path (None = backend auto-detect). The UI
# selection wins per session over this default (BUG-026, `websocket_app._resolve_session_language`).
WS_LANGUAGE_ENV_VAR = "VOICE_WS_LANGUAGE"

# Telemetry names for the live WS path (same names across transports so the pilot can chart
# active sessions + refusals per host — US-036 / TASK-WEB-030).
SESSION_STARTED_EVENT = "voice.ws.session_started"
CLIENT_CONNECTED_EVENT = "voice.ws.client_connected"
CLIENT_DISCONNECTED_EVENT = "voice.ws.client_disconnected"
ACTIVE_SESSIONS_METRIC = "voice.ws.active_sessions"
SESSION_REJECTED_EVENT = "voice.ws.session_rejected"


def ws_language_config() -> str | None:
    """Server-default language for the WS path (None = backend auto-detect)."""
    raw = os.environ.get(WS_LANGUAGE_ENV_VAR)
    return raw.strip().lower() if raw and raw.strip() else None
