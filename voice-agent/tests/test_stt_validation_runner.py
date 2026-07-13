import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stt_validation import FixtureSttProvider, SttOutcome, SttValidationRunner  # noqa: E402
from stt_validation.telemetry import TelemetryRecorder  # noqa: E402

EXPECTED_EVENTS = [
    "stt.validation.started",
    "stt.audio.accepted",
    "stt.request.started",
]


def _run(audio_path: Path, correlation_id: str) -> tuple[object, TelemetryRecorder]:
    telemetry = TelemetryRecorder()
    result = SttValidationRunner(FixtureSttProvider(), telemetry).validate(audio_path, correlation_id)
    return result, telemetry


class SttValidationRunnerTest(unittest.TestCase):
    def test_validate_returns_transcript_when_fixture_has_sidecar(self) -> None:
        # GIVEN
        with TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "question.wav"
            audio_path.write_bytes(b"fake-audio")
            audio_path.with_suffix(".txt").write_text("Why is my invoice higher?", encoding="utf-8")

            # WHEN
            result, telemetry = _run(audio_path, "corr-1")

            # THEN
            self.assertEqual(result.outcome, SttOutcome.SUCCESS)
            self.assertEqual(result.transcript, "Why is my invoice higher?")
            self.assertEqual(result.provider, "fixture-stt")
            self.assertEqual(result.correlation_id, "corr-1")
            event_names = [event.name for event in telemetry.events()]
            self.assertEqual(event_names, EXPECTED_EVENTS + ["stt.transcript.final", "stt.validation.completed"])

    def test_validate_emits_phase_spans_isolating_stt_slice(self) -> None:
        # GIVEN
        with TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "question.wav"
            audio_path.write_bytes(b"fake-audio")
            audio_path.with_suffix(".txt").write_text("Bonjour", encoding="utf-8")

            # WHEN
            _, telemetry = _run(audio_path, "corr-span")

            # THEN
            span_names = [span.name for span in telemetry.spans()]
            self.assertEqual(span_names, ["stt.audio.accept", "stt.request"])
            metric_names = [metric.name for metric in telemetry.metrics()]
            self.assertIn("stt.request.duration_ms", metric_names)
            self.assertIn("stt.validation.duration_ms", metric_names)

    def test_validate_returns_failure_when_transcript_sidecar_is_missing(self) -> None:
        # GIVEN
        with TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "question.wav"
            audio_path.write_bytes(b"fake-audio")

            # WHEN
            result, telemetry = _run(audio_path, "corr-2")

            # THEN
            self.assertEqual(result.outcome, SttOutcome.FAILED)
            self.assertEqual(result.transcript, "")
            self.assertEqual(result.error_code, "fixture_missing")
            event_names = [event.name for event in telemetry.events()]
            self.assertIn("stt.failure", event_names)
            self.assertEqual(telemetry.logs()[0].level, "warning")

    def test_validate_returns_unavailable_when_transcript_has_no_speech(self) -> None:
        # GIVEN
        with TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "silence.wav"
            audio_path.write_bytes(b"fake-audio")
            audio_path.with_suffix(".txt").write_text("   ", encoding="utf-8")

            # WHEN
            result, telemetry = _run(audio_path, "corr-silence")

            # THEN
            self.assertEqual(result.outcome, SttOutcome.UNAVAILABLE)
            self.assertEqual(result.transcript, "")
            self.assertEqual(result.error_code, "no_speech")
            event_names = [event.name for event in telemetry.events()]
            self.assertIn("stt.unavailable", event_names)
            self.assertNotIn("stt.failure", event_names)
            self.assertEqual(telemetry.logs()[0].level, "info")
            span_names = [span.name for span in telemetry.spans()]
            self.assertEqual(span_names, ["stt.audio.accept", "stt.request"])

    def test_failure_reason_is_sanitized_without_leaking_path(self) -> None:
        # GIVEN
        with TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "secret-customer.wav"

            # WHEN
            result, _ = _run(audio_path, "corr-3")

            # THEN
            self.assertEqual(result.error_code, "fixture_missing")
            self.assertNotIn(tmp_dir, result.error_reason or "")
            self.assertNotIn("secret-customer", result.error_reason or "")
            self.assertIn("<redacted-path>", result.error_reason or "")


if __name__ == "__main__":
    unittest.main()
