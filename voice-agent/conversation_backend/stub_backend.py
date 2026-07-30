from collections.abc import Iterator

from .models import AnswerOutcome, AnswerRequest, AnswerResult
from .port import EmptyTranscriptError
from .streaming import CHUNK, DONE, AnswerStreamEvent, StreamControl

# Deterministic, offline answer. Intentionally free of any digit, currency symbol
# or invoice specific so the stub can never state a fabricated amount (DEC-002).
# The real answer comes from the HTTP backend adapter (TASK-WEB-003-C); this stub
# only keeps the Voice2Voice loop answering (not echoing) for dev, tests and demos.
STUB_ANSWER_TEXT = (
    "Merci, votre demande a bien été prise en compte. "
    "Ceci est une réponse de démonstration : le détail de votre facture "
    "sera disponible une fois le service connecté."
)

# A monetary amount always needs a digit, so a digit-free text can never state one; the
# currency symbols are a belt-and-suspenders check. Kept as symbols only (not currency
# words) because the digit rule is what actually forbids a fabricated amount (DEC-002).
# Intentional parity with the production backend OutputGuardrail (DEC-002 regex), which
# is likewise digit-anchored: a spelled-out amount ("cinq euros", no digit) is out of
# scope on both paths by design, so the stub guard is neither weaker nor stronger.
_CURRENCY_SYMBOLS = ("€", "$", "£")


def assert_no_fabricated_amount(text: str) -> None:
    """Fail-fast DEC-002 invariant (RF-017): the offline stub answer must never carry a
    digit or currency symbol, so it cannot voice a fabricated amount. Enforced in the code
    path (at import) rather than only in a test, so drift on STUB_ANSWER_TEXT breaks the
    import/startup instead of silently shipping if a test were relaxed."""
    if any(ch.isdigit() for ch in text):
        raise ValueError("DEC-002 (RF-017): stub answer text must not contain a digit")
    for symbol in _CURRENCY_SYMBOLS:
        if symbol in text:
            raise ValueError(
                f"DEC-002 (RF-017): stub answer text must not contain a currency symbol ({symbol})"
            )


assert_no_fabricated_amount(STUB_ANSWER_TEXT)


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

    def answer_stream(
        self, request: AnswerRequest, control: StreamControl | None = None
    ) -> Iterator[AnswerStreamEvent]:
        # Offline streaming parity (TASK-WEB-020 / lever 1): the stub has no real
        # sentence generation, so it yields its single deterministic answer as one vetted
        # `chunk` followed by a grounded `done`. Digit/currency-free by the import-time
        # DEC-002 assertion above, so streaming can never voice a fabricated amount.
        if not request.transcript or not request.transcript.strip():
            raise EmptyTranscriptError("No transcript to answer")
        yield AnswerStreamEvent(kind=CHUNK, text=STUB_ANSWER_TEXT)
        yield AnswerStreamEvent(kind=DONE, text=STUB_ANSWER_TEXT, grounded=True)

    def warm_up(self) -> bool:
        # No cold models offline: warm-up is a symmetric no-op so the connect-time trigger
        # (TASK-WEB-021) is harmless in dev/tests and mirrors the HTTP adapter's contract.
        return True
