from dataclasses import dataclass
from enum import Enum
from typing import Any


class TtsOutcome(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    # Text was empty / had nothing to speak. Not a processing error and never
    # carries invented audio. Mirror of SttOutcome.UNAVAILABLE for the voice-out side.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    provider: str
    outcome: TtsOutcome
    duration_ms: float
    tts_request_ms: float
    correlation_id: str
    audio_format: str
    error_code: str | None = None
    error_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        # Raw audio bytes are never serialized (not JSON-safe, potentially large);
        # the byte count is exposed instead for telemetry/QA.
        return {
            "provider": self.provider,
            "outcome": self.outcome.value,
            "duration_ms": round(self.duration_ms, 3),
            "tts_request_ms": round(self.tts_request_ms, 3),
            "correlation_id": self.correlation_id,
            "audio_format": self.audio_format,
            "audio_bytes": len(self.audio),
            "error_code": self.error_code,
            "error_reason": self.error_reason,
        }
