import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from metrics import (  # noqa: E402
    GUARDRAIL_BLOCK,
    HIT,
    RETRIEVAL_EVICTION,
    VariantResult,
    aggregate,
    mean_reciprocal_rank,
    phrasing_stability,
    recall_at_k,
)


def _variant(question_id: str, ranked: tuple[str, ...], acceptable: set[str],
             variant: str = "q", answerable: bool = True) -> VariantResult:
    return VariantResult(
        question_id=question_id, variant=variant, language="fr", domain="support",
        ranked_source_ids=ranked, acceptable=frozenset(acceptable), answerable=answerable)


class FirstHitRankTest(unittest.TestCase):
    def test_returns_one_based_rank_of_first_acceptable(self):
        # GIVEN an acceptable source at the 3rd position
        v = _variant("q1", ("a", "b", "gold", "c"), {"gold"})
        # WHEN / THEN the rank is 3
        self.assertEqual(v.first_hit_rank(), 3)

    def test_returns_none_when_no_acceptable_source_present(self):
        # GIVEN no acceptable source in the ranked list
        v = _variant("q1", ("a", "b", "c"), {"gold"})
        # WHEN / THEN the rank is None
        self.assertIsNone(v.first_hit_rank())


class RecallAndRrTest(unittest.TestCase):
    def test_recall_true_within_k_and_false_beyond_k(self):
        # GIVEN the answer at rank 5
        v = _variant("q1", ("a", "b", "c", "d", "gold"), {"gold"})
        # WHEN scored at k=4 and k=8 THEN it is missed at 4, found at 8
        self.assertFalse(v.recall_at_k(4))
        self.assertTrue(v.recall_at_k(8))

    def test_reciprocal_rank_is_inverse_of_first_hit(self):
        # GIVEN the answer at rank 2 THEN RR = 0.5; absent THEN RR = 0.0
        self.assertEqual(_variant("q1", ("a", "gold"), {"gold"}).reciprocal_rank(), 0.5)
        self.assertEqual(_variant("q1", ("a", "b"), {"gold"}).reciprocal_rank(), 0.0)


class AggregationTest(unittest.TestCase):
    def test_recall_at_k_is_fraction_of_variants_that_hit(self):
        # GIVEN 2 hits within top-4 out of 4 variants
        results = [
            _variant("q1", ("gold",), {"gold"}),
            _variant("q2", ("a", "gold"), {"gold"}),
            _variant("q3", ("a", "b", "c", "d", "gold"), {"gold"}),
            _variant("q4", ("a",), {"gold"}),
        ]
        # WHEN / THEN recall@4 = 2/4
        self.assertEqual(recall_at_k(results, 4), 0.5)

    def test_mrr_is_mean_of_reciprocal_ranks(self):
        # GIVEN ranks 1 and 2
        results = [_variant("q1", ("gold",), {"gold"}),
                   _variant("q2", ("a", "gold"), {"gold"})]
        # WHEN / THEN MRR = mean(1.0, 0.5) = 0.75
        self.assertEqual(mean_reciprocal_rank(results), 0.75)


class PhrasingStabilityTest(unittest.TestCase):
    def test_question_with_agreeing_variants_is_stable(self):
        # GIVEN both variants of q1 find the answer within top-8
        results = [_variant("q1", ("gold",), {"gold"}, "bare"),
                   _variant("q1", ("gold",), {"gold"}, "Bonjour, ...")]
        # WHEN / THEN stability = 1.0 and nothing flipped
        score, unstable = phrasing_stability(results, 8)
        self.assertEqual(score, 1.0)
        self.assertEqual(unstable, [])

    def test_question_that_flips_on_phrasing_is_unstable(self):
        # GIVEN one variant finds the answer and the greeting variant does not (BUG-003)
        results = [_variant("q1", ("gold",), {"gold"}, "bare"),
                   _variant("q1", ("a", "b"), {"gold"}, "Bonjour, ...")]
        # WHEN / THEN stability = 0.0 and q1 is flagged
        score, unstable = phrasing_stability(results, 8)
        self.assertEqual(score, 0.0)
        self.assertEqual(unstable, ["q1"])


class OutcomeClassificationTest(unittest.TestCase):
    def test_hit_when_acceptable_in_top_k(self):
        # GIVEN the answer within top-8
        v = _variant("q1", ("a", "gold"), {"gold"})
        # WHEN / THEN classified as a hit
        self.assertEqual(v.outcome(8), HIT)

    def test_guardrail_block_when_no_evidence_returned(self):
        # GIVEN a blocked grounding decision (empty evidence, not answerable)
        v = _variant("q1", (), {"gold"}, answerable=False)
        # WHEN / THEN the miss is a guardrail block, not a retrieval eviction
        self.assertEqual(v.outcome(8), GUARDRAIL_BLOCK)

    def test_retrieval_eviction_when_evidence_present_but_answer_absent(self):
        # GIVEN retrieval returned evidence but no acceptable source is in top-8
        v = _variant("q1", ("a", "b", "c"), {"gold"}, answerable=True)
        # WHEN / THEN the miss is a genuine retrieval eviction
        self.assertEqual(v.outcome(8), RETRIEVAL_EVICTION)

    def test_aggregate_counts_block_and_eviction(self):
        # GIVEN one guardrail block and one retrieval eviction
        results = [
            _variant("q1", (), {"gold"}, answerable=False),
            _variant("q2", ("a", "b"), {"gold"}, answerable=True),
        ]
        # WHEN aggregated THEN each miss kind is counted
        agg = aggregate(results)
        self.assertEqual(agg.guardrail_block_variants, 1)
        self.assertEqual(agg.retrieval_eviction_variants, 1)


class AggregateTest(unittest.TestCase):
    def test_end_to_end_aggregate_counts_questions_and_variants(self):
        # GIVEN two questions, one stable+found, one flipping
        results = [
            _variant("q1", ("gold",), {"gold"}, "bare"),
            _variant("q1", ("gold",), {"gold"}, "greet"),
            _variant("q2", ("a", "b", "c", "d", "e", "f", "g", "gold"), {"gold"}, "bare"),
            _variant("q2", ("a",), {"gold"}, "greet"),
        ]
        # WHEN aggregated
        agg = aggregate(results)
        # THEN counts and the flipped question are reported
        self.assertEqual(agg.question_count, 2)
        self.assertEqual(agg.variant_count, 4)
        self.assertEqual(agg.unstable_question_ids, ["q2"])


if __name__ == "__main__":
    unittest.main()
