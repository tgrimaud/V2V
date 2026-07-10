import re
from dataclasses import dataclass

_MAX_REASON_LEN = 160

_REASON_CODES: dict[type[Exception], str] = {
    FileNotFoundError: "fixture_missing",
    ValueError: "invalid_fixture",
    TimeoutError: "stt_timeout",
}

# Surrounding punctuation is stripped before classifying a token (e.g. a trailing
# comma or period), then the whole token is replaced by a marker if sensitive.
_STRIP_CHARS = ".,;:!?()[]{}<>'\""
_PATH_SEPARATORS = ("/", "\\")

# Bare filenames with a media/data extension (no path separator required):
# e.g. `secret-customer.wav`, `recording.mp3`, `export.json`.
_SENSITIVE_EXTENSIONS = (
    "wav", "wave", "mp3", "pcm", "flac", "ogg", "m4a", "aac", "opus", "webm",
    "json", "txt", "csv", "log",
)
_FILENAME = re.compile(r"^[\w.-]+\.(?:" + "|".join(_SENSITIVE_EXTENSIONS) + r")$", re.IGNORECASE)

# Identifier-like tokens that may carry customer/session/secret data.
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_SECRET_PREFIX = re.compile(r"^(?:gsk|sk|pk|api|key|tok|token|secret|bearer)[-_].+", re.IGNORECASE)
_DIGIT_RUN = re.compile(r"^\+?\d{7,}$")  # phone / account / long numeric id
_ALNUM_ID = re.compile(r"^[A-Za-z0-9_-]{8,}$")


@dataclass(frozen=True)
class SanitizedError:
    reason_code: str
    reason: str


def sanitize_error(exc: Exception) -> SanitizedError:
    """Reduce an exception to an observable, non-sensitive failure reason.

    Raw audio bytes, filesystem paths, filenames, identifiers and billing details
    must never reach telemetry, so only the exception type (reason code) and a
    redacted, length-capped message are exposed.
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
    core = token.strip(_STRIP_CHARS)
    if not core:
        return token
    if any(sep in core for sep in _PATH_SEPARATORS):
        return "<redacted-path>"
    if _FILENAME.match(core):
        return "<redacted-file>"
    if _is_identifier(core):
        return "<redacted-id>"
    return token


def _is_identifier(core: str) -> bool:
    if _UUID.match(core) or _SECRET_PREFIX.match(core) or _DIGIT_RUN.match(core):
        return True
    # Mixed letters+digits of a meaningful length (customer ids, opaque tokens);
    # pure words and plain dates (`2026-07-10`) are intentionally kept readable.
    has_letter = any(ch.isalpha() for ch in core)
    has_digit = any(ch.isdigit() for ch in core)
    return bool(_ALNUM_ID.match(core) and has_letter and has_digit)
