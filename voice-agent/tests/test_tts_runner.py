import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tts_synthesis import (  # noqa: E402
    EMPTY_TEXT_CODE,
    FixtureTtsProvider,
    TtsOutcome,
    TtsSynthesisRunner,
)
from voice_common.telemetry import TelemetryRecorder  # noqa: E402


class _RaisingProvider:
    name = "boom-tts"
    audio_format = "pcm_16000"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def synthesize(self, text: str) -> bytes:
        raise self._exc


def _run(provider, text: str, correlation_id: str = "corr-1"):
    telemetry = TelemetryRecorder()
    result = TtsSynthesisRunner(provider, telemetry).synthesize(text, correlation_id)
    return result, telemetry


def _span(telemetry: TelemetryRecorder, name: str):
    return next((s for s in telemetry.spans() if s.name == name), None)


class TtsSynthesisRunnerTest(unittest.TestCase):
    def test_success_produces_audio_and_first_audio_span(self) -> None:
        # GIVEN the deterministic fixture provider
        provider = FixtureTtsProvider()

        # WHEN a phrase is synthesized
        result, telemetry = _run(provider, "Bonjour le monde")

        # THEN the outcome is SUCCESS with non-empty audio and the TTS slice span
        self.assertIs(result.outcome, TtsOutcome.SUCCESS)
        self.assertTrue(result.audio)
        self.assertEqual(result.audio_format, "pcm_16000")
        span = _span(telemetry, "voice.tts.first_audio")
        self.assertIsNotNone(span)
        self.assertEqual(span.attributes["outcome"], "success")
        event_names = [e.name for e in telemetry.events()]
        self.assertIn("tts.audio.final", event_names)
        self.assertIn("tts.synthesis.completed", event_names)
        metric_names = [m.name for m in telemetry.metrics()]
        self.assertIn("tts.request.duration_ms", metric_names)
        self.assertEqual(telemetry.logs()[0].level, "info")

    def test_empty_text_maps_to_unavailable_not_failed(self) -> None:
        # GIVEN the fixture provider
        provider = FixtureTtsProvider()

        # WHEN whitespace-only text is synthesized
        result, telemetry = _run(provider, "   ")

        # THEN it is UNAVAILABLE with a stable code and no invented audio
        self.assertIs(result.outcome, TtsOutcome.UNAVAILABLE)
        self.assertEqual(result.audio, b"")
        self.assertEqual(result.error_code, EMPTY_TEXT_CODE)
        event_names = [e.name for e in telemetry.events()]
        self.assertIn("tts.unavailable", event_names)
        self.assertNotIn("tts.failure", event_names)
        self.assertEqual(telemetry.logs()[0].level, "info")

    def test_provider_error_maps_to_failed_with_tts_error_code(self) -> None:
        # GIVEN a provider that raises a generic runtime failure
        provider = _RaisingProvider(RuntimeError("Gradium TTS credits exhausted"))

        # WHEN a phrase is synthesized
        result, telemetry = _run(provider, "Bonjour")

        # THEN it is FAILED with the generic tts_error code and a warning log
        self.assertIs(result.outcome, TtsOutcome.FAILED)
        self.assertEqual(result.audio, b"")
        self.assertEqual(result.error_code, "tts_error")
        self.assertIn("tts.failure", [e.name for e in telemetry.events()])
        self.assertEqual(telemetry.logs()[0].level, "warning")

    def test_timeout_maps_to_tts_timeout_outcome(self) -> None:
        # GIVEN a provider that times out
        provider = _RaisingProvider(TimeoutError("Gradium TTS request timed out"))

        # WHEN a phrase is synthesized
        result, _ = _run(provider, "Bonjour")

        # THEN the outcome is a sanitized timeout failure
        self.assertIs(result.outcome, TtsOutcome.FAILED)
        self.assertEqual(result.error_code, "tts_timeout")

    def test_sensitive_token_in_error_is_redacted_in_telemetry(self) -> None:
        # GIVEN an error carrying a secret-looking token
        provider = _RaisingProvider(RuntimeError("auth rejected key gsk_live_abc123DEF456 invalid"))

        # WHEN a phrase is synthesized
        result, telemetry = _run(provider, "Bonjour")

        # THEN the token never reaches any recorded telemetry
        dump = json.dumps(
            {
                "events": [e.attributes for e in telemetry.events()],
                "spans": [s.attributes for s in telemetry.spans()],
                "metrics": [m.attributes for m in telemetry.metrics()],
                "logs": [{"msg": lg.message, "attrs": lg.attributes} for lg in telemetry.logs()],
            },
            default=str,
        )
        self.assertIs(result.outcome, TtsOutcome.FAILED)
        self.assertNotIn("gsk_live_abc123DEF456", dump)
        self.assertIn("<redacted-id>", dump)

    def test_correlation_id_is_generated_when_absent(self) -> None:
        # GIVEN the fixture provider and no correlation id
        telemetry = TelemetryRecorder()
        runner = TtsSynthesisRunner(FixtureTtsProvider(), telemetry)

        # WHEN a phrase is synthesized without a correlation id
        result = runner.synthesize("Bonjour")

        # THEN a run id is generated and propagated to telemetry
        self.assertTrue(result.correlation_id)
        self.assertEqual(telemetry.events()[0].attributes["correlation_id"], result.correlation_id)


if __name__ == "__main__":
    unittest.main()
