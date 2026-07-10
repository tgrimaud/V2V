import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stt_validation import (  # noqa: E402
    FixtureCategory,
    FixtureSpec,
    FixtureSttProvider,
    SttValidationRunner,
    TelemetryRecorder,
    evaluate_fixture_set,
    normalize_transcript,
    word_error_rate,
)


def _runner() -> SttValidationRunner:
    return SttValidationRunner(FixtureSttProvider(), TelemetryRecorder())


def _fixture(tmp: str, name: str, hypothesis: str | None) -> Path:
    audio = Path(tmp) / f"{name}.wav"
    audio.write_bytes(b"fake-audio")
    if hypothesis is not None:
        audio.with_suffix(".txt").write_text(hypothesis, encoding="utf-8")
    return audio


class WordErrorRateTest(unittest.TestCase):
    def test_identical_transcripts_have_zero_error(self) -> None:
        self.assertEqual(word_error_rate("ma facture est elevee", "ma facture est elevee"), 0.0)

    def test_single_substitution_scales_by_reference_length(self) -> None:
        self.assertAlmostEqual(word_error_rate("ma facture est elevee", "ma facture est mentale"), 0.25)

    def test_empty_reference_with_hypothesis_is_full_error(self) -> None:
        self.assertEqual(word_error_rate("", "bonjour"), 1.0)

    def test_empty_reference_and_hypothesis_is_zero(self) -> None:
        self.assertEqual(word_error_rate("", ""), 0.0)

    def test_punctuation_only_difference_is_not_an_error(self) -> None:
        self.assertEqual(word_error_rate("Bonjour", "Bonjour."), 0.0)

    def test_case_only_difference_is_not_an_error(self) -> None:
        self.assertEqual(word_error_rate("Est-ce que", "est-ce que"), 0.0)

    def test_accent_only_difference_is_not_an_error(self) -> None:
        self.assertEqual(word_error_rate("ma facture est elevee", "ma facture est élevée"), 0.0)

    def test_combined_formatting_differences_are_not_errors(self) -> None:
        reference = "telephone, est-ce que ma facture est elevee"
        hypothesis = "Téléphone. Est-ce que ma facture est élevée ?"
        self.assertEqual(word_error_rate(reference, hypothesis), 0.0)

    def test_real_substitution_still_counts_after_normalization(self) -> None:
        self.assertAlmostEqual(word_error_rate("ma facture est élevée", "ma facture est mentale"), 0.25)

    def test_real_omission_still_counts_after_normalization(self) -> None:
        self.assertAlmostEqual(word_error_rate("ma facture est élevée", "ma facture élevée"), 0.25)


class NormalizeTranscriptTest(unittest.TestCase):
    def test_lowercases_strips_punctuation_and_accents(self) -> None:
        self.assertEqual(normalize_transcript("Téléphone, Est-ce ?"), "telephone est ce")

    def test_collapses_whitespace(self) -> None:
        self.assertEqual(normalize_transcript("  ma   facture  "), "ma facture")


class EvaluateFixtureSetTest(unittest.TestCase):
    def test_usable_fixture_above_threshold_passes(self) -> None:
        # GIVEN
        with TemporaryDirectory() as tmp:
            audio = _fixture(tmp, "q", "ma facture est mentale")
            spec = FixtureSpec("q", FixtureCategory.NOISY, audio, "ma facture est elevee", True)

            # WHEN
            report = evaluate_fixture_set(_runner(), [spec], [FixtureCategory.NOISY], quality_threshold=0.5)

            # THEN
            self.assertTrue(report.ready)
            self.assertEqual(report.assessments[0].quality_score, 0.75)
            self.assertTrue(report.assessments[0].quality_ok)

    def test_usable_fixture_below_threshold_is_flagged(self) -> None:
        # GIVEN
        with TemporaryDirectory() as tmp:
            audio = _fixture(tmp, "q", "ma facture est mentale")
            spec = FixtureSpec("q", FixtureCategory.NOISY, audio, "ma facture est elevee", True)

            # WHEN
            report = evaluate_fixture_set(_runner(), [spec], [FixtureCategory.NOISY], quality_threshold=0.9)

            # THEN
            self.assertFalse(report.ready)
            self.assertEqual(report.failed_categories(), ["noisy"])

    def test_silence_fixture_is_ok_when_no_transcript_is_invented(self) -> None:
        # GIVEN silence == empty transcript sidecar -> provider fails, no transcript
        with TemporaryDirectory() as tmp:
            audio = _fixture(tmp, "silence", "   ")
            spec = FixtureSpec("silence", FixtureCategory.SILENCE, audio, None, False)

            # WHEN
            report = evaluate_fixture_set(_runner(), [spec], [FixtureCategory.SILENCE])

            # THEN
            assessment = report.assessments[0]
            self.assertEqual(assessment.outcome, "failed")
            self.assertEqual(assessment.transcript, "")
            self.assertTrue(assessment.quality_ok)
            self.assertTrue(report.ready)

    def test_invented_transcript_for_unusable_audio_fails(self) -> None:
        # GIVEN audio expected unusable but provider returns text
        with TemporaryDirectory() as tmp:
            audio = _fixture(tmp, "silence", "bonjour je suis la")
            spec = FixtureSpec("silence", FixtureCategory.SILENCE, audio, None, False)

            # WHEN
            report = evaluate_fixture_set(_runner(), [spec], [FixtureCategory.SILENCE])

            # THEN
            self.assertFalse(report.assessments[0].quality_ok)
            self.assertFalse(report.ready)

    def test_missing_categories_are_reported_explicitly(self) -> None:
        # GIVEN only a short fixture but four categories expected
        with TemporaryDirectory() as tmp:
            audio = _fixture(tmp, "hi", "bonjour")
            spec = FixtureSpec("hi", FixtureCategory.SHORT, audio, "bonjour", True)

            # WHEN
            report = evaluate_fixture_set(
                _runner(),
                [spec],
                [FixtureCategory.SHORT, FixtureCategory.NOISY, FixtureCategory.SILENCE],
            )

            # THEN
            self.assertEqual(report.missing_categories, ["noisy", "silence"])
            self.assertFalse(report.ready)


if __name__ == "__main__":
    unittest.main()
