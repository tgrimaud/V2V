"""Deterministic closing-intent detection for end-of-call (TASK-WEB-010, ADR-0035).

Decides, from a **final** transcript, whether the customer spoke a *standalone* closing
formula ("au revoir", "merci c'est tout", "bonne journée") and, during the confirmation
turn, whether they confirmed they are done ("non", "c'est tout", "rien d'autre").

No LLM (DEC-041-b). Matching is token-based and accent-insensitive, mirroring the
`InputGuardrail` / barge-in lesson that naive `contains()` matching is fragile:
- a closing phrase is matched as a **contiguous word-token subsequence** (word-boundary,
  so "au revoir" never fires inside "aurevoirées" or a hyphenated compound);
- a **negation** immediately before the phrase ("non, pas au revoir") is rejected;
- any leftover **content** token that is not a politeness filler means the closing word
  sits inside a longer request ("avant de dire au revoir, une question") → not standalone.

Phrase sets are FR in V1 (BR-041-4) and env-tunable like the barge-in thresholds.
"""

import unicodedata
from dataclasses import dataclass

# Default FR closing formulas (each stored as a token tuple after normalisation).
DEFAULT_CLOSING_PHRASES: tuple[str, ...] = (
    "au revoir",
    "aurevoir",
    "bonne journee",
    "bonne soiree",
    "bonne fin de journee",
    "a bientot",
    "a plus tard",
    "merci au revoir",
    "merci c est tout",
    "c est tout merci",
    "je vous remercie",
    "adieu",
)

# Default FR "nothing else / I'm done" confirmations for the confirmation turn.
DEFAULT_DONE_PHRASES: tuple[str, ...] = (
    "non",
    "non merci",
    "c est tout",
    "c est bon",
    "ce sera tout",
    "rien",
    "rien d autre",
    "ca ira",
    "ca sera tout",
    "non c est bon",
    "non c est tout",
)

# Politeness tokens allowed *around* a standalone closing without making it a request.
# "non" is allowed here so "non merci, au revoir" is still a closing; a real negation of
# the farewell is caught by the negation guard below, not by this set.
FILLER_TOKENS: frozenset[str] = frozenset(
    {
        "merci",
        "beaucoup",
        "bien",
        "tres",
        "ok",
        "oui",
        "non",
        "alors",
        "donc",
        "et",
        "euh",
        "ben",
        "bon",
        "voila",
        "s",
        "il",
        "vous",
        "plait",
        "svp",
        "monsieur",
        "madame",
        "mademoiselle",
    }
)

# A negation token directly before a closing phrase negates it ("non, pas au revoir").
NEGATION_TOKENS: frozenset[str] = frozenset({"pas", "jamais", "sans", "aucun", "aucune"})


@dataclass(frozen=True)
class ClosingDecision:
    """Outcome of closing detection. `matched_phrase` is the folded phrase that fired
    (for telemetry); `rejected_reason` explains a near-miss (negation / embedded)."""

    is_closing: bool
    matched_phrase: str | None = None
    rejected_reason: str | None = None


def normalize_tokens(text: str) -> list[str]:
    """Lowercase, strip accents (NFKD, drop combining marks) and split on non-alnum.

    "Au revoir, Monsieur !" -> ["au", "revoir", "monsieur"]; "c'est tout" -> ["c","est","tout"].
    """
    folded = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    tokens: list[str] = []
    current: list[str] = []
    for ch in stripped:
        if ch.isalnum():
            current.append(ch)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _phrase_tokens(phrases: tuple[str, ...]) -> list[list[str]]:
    """Pre-tokenise phrases, longest first so "merci au revoir" wins over "au revoir"."""
    tokenised = [normalize_tokens(phrase) for phrase in phrases]
    return sorted((tok for tok in tokenised if tok), key=len, reverse=True)


def _find_phrase(tokens: list[str], phrases: list[list[str]]) -> tuple[int, int] | None:
    """Return the [start, end) span of the first phrase found as a contiguous run."""
    for phrase in phrases:
        span = _match_at_any_position(tokens, phrase)
        if span is not None:
            return span
    return None


def _match_at_any_position(tokens: list[str], phrase: list[str]) -> tuple[int, int] | None:
    last_start = len(tokens) - len(phrase)
    for start in range(last_start + 1):
        if tokens[start : start + len(phrase)] == phrase:
            return start, start + len(phrase)
    return None


class ClosingIntentDetector:
    """Word-boundary FR closing + done-confirmation detection (no LLM, ADR-0035)."""

    def __init__(
        self,
        closing_phrases: tuple[str, ...] = DEFAULT_CLOSING_PHRASES,
        done_phrases: tuple[str, ...] = DEFAULT_DONE_PHRASES,
    ) -> None:
        self._closing = _phrase_tokens(closing_phrases)
        self._done = _phrase_tokens(done_phrases)
        # Tokens accepted in a done-confirmation remainder: fillers + every token that is
        # part of a done phrase, so "non merci c'est tout" stays a confirmation.
        self._done_allowed = FILLER_TOKENS | {
            token for phrase in self._done for token in phrase
        }

    def detect_closing(self, text: str) -> ClosingDecision:
        """True only for a *standalone* closing formula (not embedded, not negated)."""
        tokens = normalize_tokens(text)
        span = _find_phrase(tokens, self._closing)
        if span is None:
            return ClosingDecision(False)
        start, end = span
        if start > 0 and tokens[start - 1] in NEGATION_TOKENS:
            return ClosingDecision(False, rejected_reason="negated")
        remainder = tokens[:start] + tokens[end:]
        if any(token not in FILLER_TOKENS for token in remainder):
            return ClosingDecision(False, rejected_reason="embedded")
        return ClosingDecision(True, matched_phrase=" ".join(tokens[start:end]))

    def is_done_confirmation(self, text: str) -> bool:
        """True when the confirmation answer means "nothing else / I'm done".

        A response that carries a real request ("non j'ai une autre question") keeps a
        non-allowed content token in the remainder → not a confirmation → the call
        continues and the question is answered.
        """
        tokens = normalize_tokens(text)
        if not tokens:
            return False
        if _find_phrase(tokens, self._done) is None:
            return False
        return all(token in self._done_allowed for token in tokens)
