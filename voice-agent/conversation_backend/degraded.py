"""Safe degraded-mode fallback (TASK-WEB-003-F).

When the backend is unavailable or not confident enough, the loop must still speak
something safe instead of failing the turn or inventing an answer. This module owns
the single safe fallback message and the builder that wraps it in a DEGRADED
`AnswerResult`.

The fallback text is intentionally free of any digit, currency symbol or invoice
specific (DEC-002): a degraded turn can never state a fabricated amount. It lives in
the neutral conversation contract so both runtimes and any adapter share one safe
message; the policy that decides *when* to degrade lives in the answer step.
"""

from .models import AnswerOutcome, AnswerRequest, AnswerResult

# Spoken to the customer when no trustworthy answer is available. No digit / amount.
DEGRADED_FALLBACK_TEXT = (
    "Je suis désolé, je ne peux pas répondre précisément à votre demande pour le "
    "moment. Un conseiller pourra vous aider ; merci de réessayer dans un instant."
)

# Below this confidence a SUCCESS answer is treated as untrustworthy and replaced by
# the safe fallback rather than risking a wrong (possibly billing) statement.
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

# Stable, non-sensitive degraded reasons (safe to log / expose as telemetry).
BACKEND_UNAVAILABLE_REASON = "backend_unavailable"
LOW_CONFIDENCE_REASON = "low_confidence"
EMPTY_ANSWER_REASON = "empty_answer"


def degraded_answer(
    request: AnswerRequest,
    *,
    provider: str,
    degraded_reason: str,
    confidence: float | None = None,
    error_code: str | None = None,
    error_reason: str | None = None,
) -> AnswerResult:
    """Build a DEGRADED result carrying the safe fallback text (never invented content)."""
    return AnswerResult(
        text=DEGRADED_FALLBACK_TEXT,
        provider=provider,
        outcome=AnswerOutcome.DEGRADED,
        correlation_id=request.correlation_id,
        confidence=confidence,
        degraded_reason=degraded_reason,
        error_code=error_code,
        error_reason=error_reason,
    )
