"""Domain-neutral error sanitization shared across the STT and TTS halves.

Reduces an exception to an observable, non-sensitive failure reason: a stable
reason code (derived from the exception type and a caller-provided `domain`
prefix) plus a redacted, length-capped message. Raw audio bytes, filesystem
paths, filenames, identifiers and billing details must never reach telemetry.

The redaction logic is intentionally domain-agnostic so both `stt_validation`
and `tts_synthesis` reuse it without importing one another. Each half supplies
its own `domain` (e.g. "stt" / "tts") and, optionally, extra exception-type
codes for concepts specific to it (e.g. STT fixture errors).
"""

import re
from dataclasses import dataclass

_MAX_REASON_LEN = 160

# Surrounding punctuation is stripped before classifying a token (e.g. a trailing
# comma or period), then the whole token is replaced by a marker if sensitive.
_STRIP_CHARS = ".,;:!?()[]{}<>'\""
_PATH_SEPARATORS = ("/", "\\")

# Known non-sensitive technical tokens (audio formats, content-types) that would
# otherwise be caught by the path/id heuristics. Kept readable so error reasons
# stay diagnostic (e.g. "unsupported format pcm_16000"). Matched case-insensitively.
_SAFE_TOKENS = frozenset(
    {
        "pcm_16000", "pcm_8000", "ulaw_8000", "alaw_8000",
        "audio/pcm", "audio/basic", "audio/wav", "audio/x-wav",
        "application/json", "application/octet-stream",
        "application/x-www-form-urlencoded",
    }
)

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


def sanitize_error(
    exc: Exception,
    *,
    domain: str = "voice",
    type_codes: dict[type[Exception], str] | None = None,
) -> SanitizedError:
    """Reduce an exception to an observable, non-sensitive failure reason.

    `domain` prefixes the generic codes (`<domain>_timeout`, `<domain>_error`).
    `type_codes` maps specific exception types to stable codes for domain concepts
    (checked first, in insertion order).
    """
    return SanitizedError(
        reason_code=_reason_code(exc, domain, type_codes or {}),
        reason=_redact(str(exc)),
    )


def _reason_code(exc: Exception, domain: str, type_codes: dict[type[Exception], str]) -> str:
    for exc_type, code in type_codes.items():
        if isinstance(exc, exc_type):
            return code
    if isinstance(exc, TimeoutError):
        return f"{domain}_timeout"
    return f"{domain}_error"


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
    if core.lower() in _SAFE_TOKENS:
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
