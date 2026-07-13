from dataclasses import dataclass
from enum import Enum
from typing import Any


class SttOutcome(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    # Audio was processed but held no usable speech (silence / no-speech). This is
    # not a processing error and never carries an invented transcript.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class TranscriptResult:
    transcript: str
    provider: str
    outcome: SttOutcome
    duration_ms: float
    stt_request_ms: float
    correlation_id: str
    error_code: str | None = None
    error_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript": self.transcript,
            "provider": self.provider,
            "outcome": self.outcome.value,
            "duration_ms": round(self.duration_ms, 3),
            "stt_request_ms": round(self.stt_request_ms, 3),
            "correlation_id": self.correlation_id,
            "error_code": self.error_code,
            "error_reason": self.error_reason,
        }
