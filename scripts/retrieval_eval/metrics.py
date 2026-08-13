"""Pure retrieval-quality metrics for the TASK-BE-027 eval harness (ADR-0032).

No I/O and no backend dependency so the scoring is unit-testable in isolation. A
"query result" is the ranked list of chunk ``source_id`` values returned by
``POST /api/conversation/retrieve`` for one question variant, paired with the set of
``acceptable_source_ids`` that genuinely answer that question.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VariantResult:
    """Outcome of one phrasing variant of a question."""

    question_id: str
    variant: str
    language: str
    domain: str
    ranked_source_ids: tuple[str, ...]
    acceptable: frozenset[str]
    error: str | None = None

    def first_hit_rank(self) -> int | None:
        """1-based rank of the first ranked source that is acceptable, else None."""
        for rank, source_id in enumerate(self.ranked_source_ids, start=1):
            if source_id in self.acceptable:
                return rank
        return None

    def recall_at_k(self, k: int) -> bool:
        """True when an acceptable source appears within the top-k ranked results."""
        rank = self.first_hit_rank()
        return rank is not None and rank <= k

    def reciprocal_rank(self) -> float:
        """1/rank of the first acceptable source, or 0.0 when none is present."""
        rank = self.first_hit_rank()
        return 1.0 / rank if rank is not None else 0.0


@dataclass
class Aggregate:
    recall_at_4: float
    recall_at_8: float
    mrr: float
    phrasing_stability: float
    variant_count: int
    question_count: int
    unstable_question_ids: list[str] = field(default_factory=list)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def recall_at_k(results: list[VariantResult], k: int) -> float:
    """Fraction of variants whose top-k contains an acceptable source."""
    return _mean([1.0 if r.recall_at_k(k) else 0.0 for r in results])


def mean_reciprocal_rank(results: list[VariantResult]) -> float:
    return _mean([r.reciprocal_rank() for r in results])


def phrasing_stability(results: list[VariantResult], k: int) -> tuple[float, list[str]]:
    """Fraction of questions whose variants all agree on the top-k outcome.

    A question "flips" when a trivial phrasing change (e.g. a greeting prefix) moves the
    answer chunk in or out of the top-k — the exact BUG-003 brittleness. Returns the
    stability score (1 - flip_rate) and the ids of the questions that flipped.
    """
    by_question: dict[str, list[VariantResult]] = {}
    for r in results:
        by_question.setdefault(r.question_id, []).append(r)
    stable = 0
    unstable_ids: list[str] = []
    for question_id, variants in by_question.items():
        outcomes = {v.recall_at_k(k) for v in variants}
        if len(outcomes) == 1:
            stable += 1
        else:
            unstable_ids.append(question_id)
    score = stable / len(by_question) if by_question else 0.0
    return score, unstable_ids


def aggregate(results: list[VariantResult], stability_k: int = 8) -> Aggregate:
    stability, unstable = phrasing_stability(results, stability_k)
    question_ids = {r.question_id for r in results}
    return Aggregate(
        recall_at_4=recall_at_k(results, 4),
        recall_at_8=recall_at_k(results, 8),
        mrr=mean_reciprocal_rank(results),
        phrasing_stability=stability,
        variant_count=len(results),
        question_count=len(question_ids),
        unstable_question_ids=sorted(unstable),
    )
