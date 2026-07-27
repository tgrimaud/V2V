import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_voice.closing_intent import (  # noqa: E402
    ClosingIntentDetector,
    normalize_tokens,
)


class NormalizeTokensTest(unittest.TestCase):
    def test_strips_accents_case_and_punctuation(self) -> None:
        # GIVEN a mixed-case accented sentence with punctuation
        # WHEN it is normalised
        tokens = normalize_tokens("Au revoir, Monsieur !")
        # THEN it becomes accent-folded lowercase word tokens
        self.assertEqual(["au", "revoir", "monsieur"], tokens)

    def test_folds_accented_closing(self) -> None:
        # GIVEN "bonne journée" with an accent
        # WHEN normalised
        # THEN the accent is folded so it matches the accent-free phrase list
        self.assertEqual(["bonne", "journee"], normalize_tokens("Bonne journée"))

    def test_empty_text_yields_no_tokens(self) -> None:
        # GIVEN punctuation-only / blank input
        # WHEN normalised
        # THEN no tokens are produced
        self.assertEqual([], normalize_tokens("   ...  "))


class DetectClosingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = ClosingIntentDetector()

    def test_fires_on_a_standalone_farewell(self) -> None:
        # GIVEN a bare closing formula
        # WHEN detection runs
        decision = self.detector.detect_closing("Au revoir")
        # THEN it is recognised as a closing and reports the matched phrase
        self.assertTrue(decision.is_closing)
        self.assertEqual("au revoir", decision.matched_phrase)

    def test_fires_with_only_politeness_fillers_around_it(self) -> None:
        # GIVEN a closing wrapped in politeness tokens
        # WHEN detection runs
        decision = self.detector.detect_closing("Merci beaucoup, au revoir monsieur")
        # THEN the fillers do not make it a request; still a standalone closing
        self.assertTrue(decision.is_closing)

    def test_does_not_fire_on_a_closing_word_inside_a_longer_request(self) -> None:
        # GIVEN a closing word embedded in a real request (AC scenario 2)
        # WHEN detection runs
        decision = self.detector.detect_closing(
            "avant de dire au revoir, j'ai une question sur ma facture"
        )
        # THEN the leftover content tokens mark it as embedded, not a closing
        self.assertFalse(decision.is_closing)
        self.assertEqual("embedded", decision.rejected_reason)

    def test_does_not_fire_when_the_farewell_is_negated(self) -> None:
        # GIVEN an explicit negation right before the closing phrase
        # WHEN detection runs
        decision = self.detector.detect_closing("non, pas au revoir")
        # THEN the negation guard rejects it
        self.assertFalse(decision.is_closing)
        self.assertEqual("negated", decision.rejected_reason)

    def test_matches_on_word_boundaries_not_substrings(self) -> None:
        # GIVEN a word that merely contains the closing letters as a substring
        # WHEN detection runs
        decision = self.detector.detect_closing("aurevoirement bidon")
        # THEN a substring is not a match (word-boundary matching, not contains())
        self.assertFalse(decision.is_closing)

    def test_accepts_non_merci_before_the_farewell(self) -> None:
        # GIVEN "non merci" (no thanks) followed by the farewell — not a negation of it
        # WHEN detection runs
        decision = self.detector.detect_closing("non merci, au revoir")
        # THEN it is still a standalone closing (the token before "au" is "merci")
        self.assertTrue(decision.is_closing)


class IsDoneConfirmationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = ClosingIntentDetector()

    def test_a_bare_no_confirms_done(self) -> None:
        # GIVEN a lone "non" answer to "anything else?"
        # WHEN evaluated
        # THEN the customer is done
        self.assertTrue(self.detector.is_done_confirmation("Non"))

    def test_cest_tout_confirms_done(self) -> None:
        # GIVEN "non merci, c'est tout"
        # WHEN evaluated
        # THEN it is a done confirmation despite the extra done/filler tokens
        self.assertTrue(self.detector.is_done_confirmation("Non merci, c'est tout"))

    def test_a_new_question_does_not_confirm_done(self) -> None:
        # GIVEN a "no" that carries a real follow-up request
        # WHEN evaluated
        # THEN it is NOT a confirmation, so the call continues and answers the question
        self.assertFalse(
            self.detector.is_done_confirmation("non, j'ai une autre question")
        )

    def test_a_plain_yes_does_not_confirm_done(self) -> None:
        # GIVEN a bare "oui" (ambiguous, not a clear "I'm done")
        # WHEN evaluated
        # THEN it does not end the call (end only on an explicit done / silence)
        self.assertFalse(self.detector.is_done_confirmation("oui"))

    def test_silence_is_not_a_done_confirmation_here(self) -> None:
        # GIVEN an empty transcript (silence is handled by the confirmation timer, not here)
        # WHEN evaluated
        # THEN the text-based check does not itself confirm done
        self.assertFalse(self.detector.is_done_confirmation(""))


class EnvTunablePhrasesTest(unittest.TestCase):
    def test_honours_a_custom_closing_phrase_list(self) -> None:
        # GIVEN a detector configured with a custom closing phrase
        detector = ClosingIntentDetector(closing_phrases=("terminado",))
        # WHEN the custom phrase is spoken
        # THEN it fires, and the default "au revoir" no longer does
        self.assertTrue(detector.detect_closing("terminado").is_closing)
        self.assertFalse(detector.detect_closing("au revoir").is_closing)


if __name__ == "__main__":
    unittest.main()
