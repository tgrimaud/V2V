"""Client-safe error bodies for the voice HTTP endpoints (TASK-WEB-006, RF-013).

The `502` responses of `/api/voice/stt`, `/api/voice/tts` and `/api/voice/turn`
must never echo raw provider exception text. Even after sanitization redacts
paths/ids/secrets (RF-001/RF-009), generic provider wording could still reach the
client. This module maps a failed turn to a stable `error_code`, the request
`correlation_id` and a generic, author-controlled `message` — the same trade-off
the Java backend makes with `ERR_UPSTREAM` + correlation id. The full sanitized
reason stays server-side in the telemetry events written by `_log_turn`.

Only author-controlled strings ever reach the body here; nothing is derived from
the provider exception text, so no internal wording can leak.
"""

from typing import Any

# Default shown when an error code has no specific client-facing message. Kept
# deliberately vague: the machine-readable detail is the stable `error_code`.
GENERIC_VOICE_ERROR = "The voice service could not process this request. Please try again."

# Author-controlled, non-sensitive messages for the client-actionable codes. These
# are safe because they describe our own stable codes, not the provider exception.
_CLIENT_MESSAGES: dict[str, str] = {
    "no_speech": "No speech was detected. Please try speaking again.",
    "empty_text": "There was nothing to say for this turn.",
    "empty_answer": "There was nothing to say for this turn.",
    "stt_timeout": "The voice service timed out. Please try again.",
    "tts_timeout": "The voice service timed out. Please try again.",
    "backend_timeout": "The voice service timed out. Please try again.",
    "no_transcript": "No speech could be transcribed from the audio.",
    "no_audio": "No audio answer could be produced for this turn.",
}

# Fallback code when the failing result carried none (defensive; runners always set one).
DEFAULT_ERROR_CODE = "voice_error"


class SessionCapacityError(RuntimeError):
    """Raised when a new WebRTC session is refused because the concurrency cap is reached.

    Lives in this lightweight module (no pipecat/webrtc imports) so the HTTP server can
    catch it and answer 503 without importing the WebRTC signaling module — server.py
    must still start when the WebRTC extra / pipecat is absent (TASK-WEB-024).
    """

    def __init__(self, active: int, cap: int) -> None:
        super().__init__(f"WebRTC session cap reached ({active}/{cap})")
        self.active = active
        self.cap = cap


def client_error_body(
    error_code: str | None,
    correlation_id: str | None,
    outcome: str = "failed",
) -> dict[str, Any]:
    """Build the client-safe JSON body for a failed voice turn.

    Carries only the stable `error_code`, the `correlation_id` and a generic
    `message`; the raw provider reason is intentionally omitted from the body.
    """
    code = error_code or DEFAULT_ERROR_CODE
    return {
        "outcome": outcome,
        "error_code": code,
        "correlation_id": correlation_id,
        "message": _CLIENT_MESSAGES.get(code, GENERIC_VOICE_ERROR),
    }
