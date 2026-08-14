"""Select the conversation backend at runtime (TASK-WEB-003-C).

`stub` (default) keeps the deterministic offline answer; `http` builds the real
HTTP adapter from environment configuration. Backend choice is a runtime decision
(`--backend {stub,http}`, env `VOICE_BACKEND`) so QA can run either without code
changes and providers stay replaceable behind the `BackendAnswerPort`.
"""

import os

from .http_backend import DEFAULT_TIMEOUT_S, HttpBackendAdapter
from .port import BackendAnswerPort
from .stub_backend import StubBackendAdapter

STUB = "stub"
HTTP = "http"
BACKEND_NAMES = (STUB, HTTP)

ENDPOINT_ENV_VAR = "VOICE_BACKEND_URL"
API_KEY_ENV_VAR = "VOICE_BACKEND_API_KEY"
TIMEOUT_ENV_VAR = "VOICE_BACKEND_TIMEOUT_S"

# VOICE_BACKEND_URL is the backend *server* base (e.g. http://host:8080 or the backend
# VIP), so operators configure only the server, not the internal REST layout. The fixed
# conversation path is appended here (BUG-013); HttpBackendAdapter then derives the
# /converse-stream and /warm-up siblings from the resulting converse URL.
CONVERSE_PATH = "/api/conversation/converse"


def build_backend(name: str = STUB) -> BackendAnswerPort:
    if name == STUB:
        return StubBackendAdapter()
    if name == HTTP:
        return _build_http()
    raise ValueError(f"Unknown conversation backend '{name}'; expected one of {BACKEND_NAMES}")


def _build_http() -> HttpBackendAdapter:
    base_url = os.environ.get(ENDPOINT_ENV_VAR)
    if not base_url:
        raise ValueError(f"{ENDPOINT_ENV_VAR} must be set to use the http backend")
    return HttpBackendAdapter(
        _converse_endpoint(base_url),
        api_key=os.environ.get(API_KEY_ENV_VAR),
        timeout_s=_timeout(),
    )


def _converse_endpoint(base_url: str) -> str:
    """Build the converse endpoint from the configured server base URL.

    Idempotent for backward compatibility: a value that already ends with the converse
    path (e.g. a full ".../api/conversation/converse" from an older config) is kept
    as-is rather than doubled, so upgrading the config to a bare base URL is optional.
    """
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/converse"):
        return trimmed
    return trimmed + CONVERSE_PATH


def _timeout() -> float:
    raw = os.environ.get(TIMEOUT_ENV_VAR)
    return float(raw) if raw else DEFAULT_TIMEOUT_S
