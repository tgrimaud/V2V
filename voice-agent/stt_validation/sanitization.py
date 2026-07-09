from dataclasses import dataclass

_MAX_REASON_LEN = 160

_REASON_CODES: dict[type[Exception], str] = {
    FileNotFoundError: "fixture_missing",
    ValueError: "invalid_fixture",
    TimeoutError: "stt_timeout",
}


@dataclass(frozen=True)
class SanitizedError:
    reason_code: str
    reason: str


def sanitize_error(exc: Exception) -> SanitizedError:
    """Reduce an exception to an observable, non-sensitive failure reason.

    Raw audio bytes, filesystem paths and billing details must never reach
    telemetry, so only the exception type (reason code) and a redacted,
    length-capped message are exposed.
    """
    reason_code = _reason_code(exc)
    return SanitizedError(reason_code=reason_code, reason=_redact(str(exc)))


def _reason_code(exc: Exception) -> str:
    for exc_type, code in _REASON_CODES.items():
        if isinstance(exc, exc_type):
            return code
    return "stt_error"


def _redact(message: str) -> str:
    tokens = [_redact_token(token) for token in message.split()]
    redacted = " ".join(tokens).strip()
    if len(redacted) > _MAX_REASON_LEN:
        return redacted[:_MAX_REASON_LEN].rstrip() + "..."
    return redacted


def _redact_token(token: str) -> str:
    if "/" in token or "\\" in token:
        return "<redacted-path>"
    return token
