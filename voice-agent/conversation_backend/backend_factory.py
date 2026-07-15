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


def build_backend(name: str = STUB) -> BackendAnswerPort:
    if name == STUB:
        return StubBackendAdapter()
    if name == HTTP:
        return _build_http()
    raise ValueError(f"Unknown conversation backend '{name}'; expected one of {BACKEND_NAMES}")


def _build_http() -> HttpBackendAdapter:
    endpoint = os.environ.get(ENDPOINT_ENV_VAR)
    if not endpoint:
        raise ValueError(f"{ENDPOINT_ENV_VAR} must be set to use the http backend")
    return HttpBackendAdapter(
        endpoint,
        api_key=os.environ.get(API_KEY_ENV_VAR),
        timeout_s=_timeout(),
    )


def _timeout() -> float:
    raw = os.environ.get(TIMEOUT_ENV_VAR)
    return float(raw) if raw else DEFAULT_TIMEOUT_S
