"""STT-facing view of the shared error sanitizer.

The redaction logic now lives in the domain-neutral `voice_common` package so the
TTS half can reuse it without importing `stt_validation`. This module keeps the
STT reason codes (`stt_timeout`, `stt_error`, plus the fixture-specific
`fixture_missing` / `invalid_fixture`) and the existing no-argument call surface.
"""

from voice_common.sanitization import SanitizedError
from voice_common.sanitization import sanitize_error as _sanitize

# STT fixture-specific reason codes (checked before the generic domain codes).
_STT_TYPE_CODES: dict[type[Exception], str] = {
    FileNotFoundError: "fixture_missing",
    ValueError: "invalid_fixture",
}

__all__ = ["SanitizedError", "sanitize_error"]


def sanitize_error(exc: Exception) -> SanitizedError:
    return _sanitize(exc, domain="stt", type_codes=_STT_TYPE_CODES)
