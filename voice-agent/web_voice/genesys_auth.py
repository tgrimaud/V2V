"""Genesys AudioHook connection authentication policy + telemetry (TASK-INFRA-012).

Verifies the connection-auth handshake Genesys Cloud sends when it initiates an
AudioHook ``wss`` session, BEFORE the session is built (`genesys_app.py`):

1. an **API key** in the ``X-API-KEY`` header, matched constant-time against the
   configured key (``GENESYS_AUDIOHOOK_API_KEY``);
2. an **HMAC-SHA256 signature** over the canonicalized request components
   (`genesys_signature.py`), keyed by the base64-decoded shared secret
   (``GENESYS_AUDIOHOOK_SECRET``), compared constant-time.

Fail-closed posture (ADR-0049 review Major #2): when the endpoint is enabled but no
API key + secret is configured, EVERY connection is refused (`rejected_not_configured`)
— never opened. The Origin allowlist stays as defense-in-depth in the handler.

Telemetry: one bounded-cardinality auth-outcome event + metric per attempt on the
Genesys channel (outcome in {accepted, rejected_bad_signature, rejected_missing_key,
rejected_not_configured}). The pre-session auth may have no conversationId yet, so a
connection-scoped correlation id (Genesys session id, else a fresh uuid) is used and
tagged ``auth_scope``. NO secret, signature, API key or PII is ever logged/spanned.

TODO(TASK-INFRA-012: live-measurement): the negotiated API-key header casing, the
signed ``@request-target``/``@authority`` as seen behind the pilot HAProxy edge, and
any org-id allowlist must be confirmed against the live Genesys tenant; all are
env-configurable so live values drop in without a code change.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from voice_common.telemetry import TelemetryRecorder
from voice_common.trace_context import derive_traceparent

from .envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL
from .genesys_signature import build_signature_base, parse_signature_headers

API_KEY_ENV_VAR = "GENESYS_AUDIOHOOK_API_KEY"
SECRET_ENV_VAR = "GENESYS_AUDIOHOOK_SECRET"
API_KEY_HEADER_ENV_VAR = "GENESYS_AUDIOHOOK_API_KEY_HEADER"
MAX_AGE_ENV_VAR = "GENESYS_AUDIOHOOK_SIGNATURE_MAX_AGE_S"
AUTHORITY_ENV_VAR = "GENESYS_AUDIOHOOK_AUTHORITY"

DEFAULT_API_KEY_HEADER = "X-API-KEY"
DEFAULT_MAX_SIGNATURE_AGE_S = 300.0

AUTH_EVENT = "voice.genesys.connection_auth"
AUTH_OUTCOME_METRIC = "voice.genesys.auth_outcome"
OUTCOME_ACCEPTED = "accepted"
OUTCOME_BAD_SIGNATURE = "rejected_bad_signature"
OUTCOME_MISSING_KEY = "rejected_missing_key"
OUTCOME_NOT_CONFIGURED = "rejected_not_configured"

_HTTP_STATUS = {
    OUTCOME_MISSING_KEY: 401,
    OUTCOME_BAD_SIGNATURE: 401,
    OUTCOME_NOT_CONFIGURED: 503,
}


@dataclass(frozen=True)
class GenesysAuthConfig:
    api_key: str = ""
    secret: bytes = b""
    api_key_header: str = DEFAULT_API_KEY_HEADER
    max_signature_age_s: float = DEFAULT_MAX_SIGNATURE_AGE_S
    authority_override: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key) and bool(self.secret)


@dataclass(frozen=True)
class AuthResult:
    outcome: str

    @property
    def ok(self) -> bool:
        return self.outcome == OUTCOME_ACCEPTED

    @property
    def http_status(self) -> int:
        return _HTTP_STATUS.get(self.outcome, 401)


def resolve_auth_config_from_env() -> GenesysAuthConfig:
    """Resolve the AudioHook auth config from env (unconfigured -> fail-closed)."""
    return GenesysAuthConfig(
        api_key=(os.environ.get(API_KEY_ENV_VAR) or "").strip(),
        secret=_decode_secret(os.environ.get(SECRET_ENV_VAR)),
        api_key_header=(os.environ.get(API_KEY_HEADER_ENV_VAR) or DEFAULT_API_KEY_HEADER).strip(),
        max_signature_age_s=_float_env(MAX_AGE_ENV_VAR, DEFAULT_MAX_SIGNATURE_AGE_S),
        authority_override=(os.environ.get(AUTHORITY_ENV_VAR) or "").strip() or None,
    )


@dataclass
class GenesysConnectionAuthenticator:
    config: GenesysAuthConfig
    telemetry_factory: Callable[[], TelemetryRecorder] = TelemetryRecorder
    log: Callable[[TelemetryRecorder], None] = field(default=lambda _r: None)
    now: Callable[[], float] = time.time

    @property
    def configured(self) -> bool:
        return self.config.configured

    def authenticate(self, request: Any) -> AuthResult:
        outcome = self._verify(request)
        self._record(request, outcome)
        return AuthResult(outcome)

    def _verify(self, request: Any) -> str:
        if not self.config.configured:
            return OUTCOME_NOT_CONFIGURED
        if not self._api_key_ok(request):
            return OUTCOME_MISSING_KEY
        return self._signature_outcome(request)

    def _api_key_ok(self, request: Any) -> bool:
        presented = request.headers.get(self.config.api_key_header, "")
        return bool(presented) and hmac.compare_digest(presented, self.config.api_key)

    def _signature_outcome(self, request: Any) -> str:
        sig_input = parse_signature_headers(request.headers)
        if sig_input is None or self._expired(sig_input.params):
            return OUTCOME_BAD_SIGNATURE
        base = build_signature_base(request, sig_input, self.config.authority_override)
        if base is None:
            return OUTCOME_BAD_SIGNATURE
        expected = hmac.new(self.config.secret, base.encode("utf-8"), hashlib.sha256).digest()
        matched = hmac.compare_digest(expected, sig_input.signature)
        return OUTCOME_ACCEPTED if matched else OUTCOME_BAD_SIGNATURE

    def _expired(self, params: dict[str, str]) -> bool:
        expires = params.get("expires")
        if not expires:
            return False
        try:
            return self.now() > float(expires) + self.config.max_signature_age_s
        except ValueError:
            return True

    def _record(self, request: Any, outcome: str) -> None:
        cid, scope = _auth_correlation(request)
        telemetry = self.telemetry_factory()
        telemetry.record(
            AUTH_EVENT,
            correlation_id=cid,
            channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
            outcome=outcome,
            auth_scope=scope,
            traceparent=derive_traceparent(cid),
        )
        telemetry.metric(
            AUTH_OUTCOME_METRIC,
            1.0,
            correlation_id=cid,
            channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
            outcome=outcome,
        )
        self.log(telemetry)


def genesys_authenticator_from_env(
    telemetry_factory: Callable[[], TelemetryRecorder] = TelemetryRecorder,
    log: Callable[[TelemetryRecorder], None] = lambda _r: None,
) -> GenesysConnectionAuthenticator:
    return GenesysConnectionAuthenticator(
        resolve_auth_config_from_env(), telemetry_factory=telemetry_factory, log=log
    )


def _auth_correlation(request: Any) -> tuple[str, str]:
    """(correlation_id, auth_scope): conversationId if present, else connection-scoped."""
    conversation = request.query.get("conversationId") or request.query.get("conversation_id")
    if conversation:
        return conversation, "conversation"
    session = request.headers.get("Audiohook-Session-Id")
    return (session, "connection") if session else (str(uuid4()), "connection")


def _decode_secret(raw: str | None) -> bytes:
    if not raw or not raw.strip():
        return b""
    stripped = raw.strip()
    padded = stripped + "=" * ((-len(stripped)) % 4)
    try:
        return base64.b64decode(padded)
    except (binascii.Error, ValueError):
        return b""


def _float_env(env_var: str, default: float) -> float:
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default
