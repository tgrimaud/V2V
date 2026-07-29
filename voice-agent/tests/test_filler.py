"""Tests for the spoken filler config module (TASK-WEB-019, delivers US-020).

These cover the pure config surface: the enable flag, the env-tunable perceived-wait
threshold, the phrase override parsing (with the DEC-002 digit guard) and the random
phrase pick. The timer wiring is tested against `AnswerProcessor` in
`test_answer_processor.py`.
"""

import random
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from voice_pipeline.filler import (  # noqa: E402
    DEFAULT_FILLER_PHRASES,
    DEFAULT_FILLER_THRESHOLD_MS,
    filler_enabled,
    pick_phrase,
    resolve_filler_phrases,
    resolve_filler_threshold_ms,
)


class FillerEnabledTest(unittest.TestCase):
    def test_enabled_by_default_when_unset(self) -> None:
        # GIVEN no override -> THEN the filler is on (voice default)
        self.assertTrue(filler_enabled({}))

    def test_disable_values_turn_it_off(self) -> None:
        # GIVEN an explicit off value -> THEN the filler is disabled
        for value in ("0", "false", "no", "off", "", "  Off  "):
            self.assertFalse(filler_enabled({"VOICE_FILLER_ENABLED": value}), value)

    def test_other_values_keep_it_on(self) -> None:
        # GIVEN any non-off value -> THEN the filler stays on
        self.assertTrue(filler_enabled({"VOICE_FILLER_ENABLED": "1"}))
        self.assertTrue(filler_enabled({"VOICE_FILLER_ENABLED": "yes"}))


class FillerThresholdTest(unittest.TestCase):
    def test_unset_falls_back_to_default(self) -> None:
        self.assertEqual(resolve_filler_threshold_ms({}), DEFAULT_FILLER_THRESHOLD_MS)

    def test_valid_override_is_honoured(self) -> None:
        self.assertEqual(resolve_filler_threshold_ms({"VOICE_FILLER_THRESHOLD_MS": "800"}), 800.0)

    def test_non_numeric_degrades_to_default(self) -> None:
        self.assertEqual(resolve_filler_threshold_ms({"VOICE_FILLER_THRESHOLD_MS": "soon"}), DEFAULT_FILLER_THRESHOLD_MS)

    def test_non_positive_degrades_to_default(self) -> None:
        # GIVEN zero / negative (a wait threshold must be > 0) -> THEN fall back
        self.assertEqual(resolve_filler_threshold_ms({"VOICE_FILLER_THRESHOLD_MS": "0"}), DEFAULT_FILLER_THRESHOLD_MS)
        self.assertEqual(resolve_filler_threshold_ms({"VOICE_FILLER_THRESHOLD_MS": "-5"}), DEFAULT_FILLER_THRESHOLD_MS)


class FillerPhrasesTest(unittest.TestCase):
    def test_unset_uses_the_builtin_set(self) -> None:
        self.assertEqual(resolve_filler_phrases({}), DEFAULT_FILLER_PHRASES)

    def test_override_is_pipe_separated_and_trimmed(self) -> None:
        phrases = resolve_filler_phrases({"VOICE_FILLER_PHRASES": " Un instant | Je regarde "})
        self.assertEqual(phrases, ("Un instant", "Je regarde"))

    def test_digit_bearing_phrases_are_dropped_dec_002(self) -> None:
        # GIVEN an override where one phrase carries a figure (forbidden by DEC-002)
        phrases = resolve_filler_phrases({"VOICE_FILLER_PHRASES": "Un instant|Votre facture est 42 euros"})
        # THEN the digit-bearing phrase is dropped, the safe one kept
        self.assertEqual(phrases, ("Un instant",))

    def test_all_unsafe_or_empty_override_falls_back_to_default(self) -> None:
        # GIVEN an override that leaves nothing safe -> THEN the built-in set is used
        self.assertEqual(resolve_filler_phrases({"VOICE_FILLER_PHRASES": "12|  "}), DEFAULT_FILLER_PHRASES)

    def test_default_phrases_carry_no_digit(self) -> None:
        # DEC-002: a holding phrase can never state a figure
        for phrase in DEFAULT_FILLER_PHRASES:
            self.assertFalse(any(ch.isdigit() for ch in phrase), phrase)


class PickPhraseTest(unittest.TestCase):
    def test_pick_returns_a_member_of_the_set(self) -> None:
        phrases = ("a", "b", "c")
        self.assertIn(pick_phrase(phrases, rng=random.Random(1)), phrases)

    def test_pick_is_deterministic_with_a_seeded_rng(self) -> None:
        # GIVEN the same seed -> THEN the same phrase (repeatable for tests)
        first = pick_phrase(("x", "y", "z"), rng=random.Random(7))
        second = pick_phrase(("x", "y", "z"), rng=random.Random(7))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
