from dataclasses import dataclass
from enum import Enum
from typing import Any


class SttOutcome(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True)
class TranscriptResult:
    transcript: str
    provider: str
    outcome: SttOutcome
    duration_ms: float
    correlation_id: str
    error_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript": self.transcript,
            "provider": self.provider,
            "outcome": self.outcome.value,
            "duration_ms": round(self.duration_ms, 3),
            "correlation_id": self.correlation_id,
            "error_reason": self.error_reason,
        }
