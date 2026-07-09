import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stt_validation import FixtureSttProvider, SttOutcome, SttValidationRunner  # noqa: E402
from stt_validation.telemetry import TelemetryRecorder  # noqa: E402


class SttValidationRunnerTest(unittest.TestCase):
    def test_validate_returns_transcript_when_fixture_has_sidecar(self) -> None:
        # GIVEN
        with TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "question.wav"
            audio_path.write_bytes(b"fake-audio")
            audio_path.with_suffix(".txt").write_text("Why is my invoice higher?", encoding="utf-8")
            telemetry = TelemetryRecorder()

            # WHEN
            result = SttValidationRunner(FixtureSttProvider(), telemetry).validate(audio_path, "corr-1")

            # THEN
            self.assertEqual(result.outcome, SttOutcome.SUCCESS)
            self.assertEqual(result.transcript, "Why is my invoice higher?")
            self.assertEqual(result.provider, "fixture-stt")
            self.assertEqual(result.correlation_id, "corr-1")
            self.assertEqual(len(telemetry.events()), 2)
            self.assertEqual(len(telemetry.metrics()), 1)
            self.assertEqual(len(telemetry.logs()), 1)

    def test_validate_returns_failure_when_transcript_sidecar_is_missing(self) -> None:
        # GIVEN
        with TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "question.wav"
            audio_path.write_bytes(b"fake-audio")
            telemetry = TelemetryRecorder()

            # WHEN
            result = SttValidationRunner(FixtureSttProvider(), telemetry).validate(audio_path, "corr-2")

            # THEN
            self.assertEqual(result.outcome, SttOutcome.FAILED)
            self.assertEqual(result.transcript, "")
            self.assertIn("Transcript fixture not found", result.error_reason or "")
            self.assertEqual(len(telemetry.events()), 2)
            self.assertEqual(telemetry.metrics()[0].attributes["outcome"], "failed")
            self.assertIn("error_reason", telemetry.logs()[0].attributes)


if __name__ == "__main__":
    unittest.main()
