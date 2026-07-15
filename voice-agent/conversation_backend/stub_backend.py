from .models import AnswerOutcome, AnswerRequest, AnswerResult
from .port import EmptyTranscriptError

# Deterministic, offline answer. Intentionally free of any digit, currency symbol
# or invoice specific so the stub can never state a fabricated amount (DEC-002).
# The real answer comes from the HTTP backend adapter (TASK-WEB-003-C); this stub
# only keeps the Voice2Voice loop answering (not echoing) for dev, tests and demos.
STUB_ANSWER_TEXT = (
    "Merci, votre demande a bien été prise en compte. "
    "Ceci est une réponse de démonstration : le détail de votre facture "
    "sera disponible une fois le service connecté."
)


class StubBackendAdapter:
    """Deterministic offline BackendAnswerPort adapter (default for dev/tests)."""

    name = "stub-backend"

    def answer(self, request: AnswerRequest) -> AnswerResult:
        if not request.transcript or not request.transcript.strip():
            raise EmptyTranscriptError("No transcript to answer")
        return AnswerResult(
            text=STUB_ANSWER_TEXT,
            provider=self.name,
            outcome=AnswerOutcome.SUCCESS,
            correlation_id=request.correlation_id,
        )
