from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class AnswerOutcome(str, Enum):
    SUCCESS = "success"
    # The backend answered but with low confidence or a safe fallback (no invented
    # billing content). The caller still speaks something; the turn is flagged degraded.
    DEGRADED = "degraded"
    # Nothing to answer (empty transcript). Not a processing error and never carries
    # invented content. Mirror of TtsOutcome.UNAVAILABLE / SttOutcome.UNAVAILABLE.
    UNAVAILABLE = "unavailable"


class ConversationEnvelope(Protocol):
    """Structural view of the traceability fields needed from a channel envelope.

    web_voice.ChannelEnvelope satisfies this without conversation_backend importing
    web_voice, so the neutral middle stays decoupled from both voice halves and the
    web transport.
    """

    channel: str
    conversation_id: str
    correlation_id: str


@dataclass(frozen=True)
class AnswerRequest:
    transcript: str
    correlation_id: str
    conversation_id: str
    channel: str
    # US-042: optional UI-selected answer language ("fr"/"en"). Forwarded to the backend
    # so it forces the answer language instead of auto-detecting; None keeps detection.
    language: str | None = None

    @classmethod
    def from_envelope(cls, transcript: str, envelope: ConversationEnvelope) -> "AnswerRequest":
        return cls(
            transcript=transcript,
            correlation_id=envelope.correlation_id,
            conversation_id=envelope.conversation_id,
            channel=envelope.channel,
            language=getattr(envelope, "language", None),
        )

    def to_dict(self) -> dict[str, Any]:
        # The transcript can carry personal data; expose only its length for
        # telemetry/QA, never the raw text. Language is a non-sensitive selector.
        return {
            "channel": self.channel,
            "conversation_id": self.conversation_id,
            "correlation_id": self.correlation_id,
            "transcript_chars": len(self.transcript),
            "language": self.language,
        }


@dataclass(frozen=True)
class AnswerResult:
    text: str
    provider: str
    outcome: AnswerOutcome
    correlation_id: str
    confidence: float | None = None
    degraded_reason: str | None = None
    duration_ms: float = 0.0
    error_code: str | None = None
    error_reason: str | None = None

    @property
    def is_success(self) -> bool:
        return self.outcome is AnswerOutcome.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        # The response text is customer-visible content; expose its length for
        # telemetry/QA, never the raw text.
        return {
            "provider": self.provider,
            "outcome": self.outcome.value,
            "correlation_id": self.correlation_id,
            "confidence": self.confidence,
            "degraded_reason": self.degraded_reason,
            "duration_ms": round(self.duration_ms, 3),
            "text_chars": len(self.text),
            "error_code": self.error_code,
            "error_reason": self.error_reason,
        }
