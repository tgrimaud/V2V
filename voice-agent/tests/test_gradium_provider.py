import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stt_validation import (  # noqa: E402
    GradiumResponse,
    GradiumSttError,
    GradiumSttProvider,
    NoSpeechDetectedError,
    SttOutcome,
    SttValidationRunner,
    TelemetryRecorder,
    build_provider,
)

API_KEY = "super-secret-key-should-never-leak"


def _transport(status: int = 200, body: str = "", captured: dict | None = None):
    def transport(url, headers, params, content, timeout):
        if captured is not None:
            captured["headers"] = headers
            captured["params"] = params
        return GradiumResponse(status=status, body=body)

    return transport


def _provider(transport) -> GradiumSttProvider:
    return GradiumSttProvider(API_KEY, transport=transport)


def _audio(tmp: str) -> Path:
    audio = Path(tmp) / "clip.wav"
    audio.write_bytes(b"\x00\x01")
    return audio


class GradiumTranscribeTest(unittest.TestCase):
    def test_successful_response_joins_text_tokens(self) -> None:
        # GIVEN a Gradium response with line-delimited text tokens
        body = '{"type": "text", "text": "Bonjour"}\n{"type": "text", "text": "monde"}'
        provider = _provider(_transport(200, body))
        with TemporaryDirectory() as tmp:
            # WHEN the audio is transcribed
            transcript = provider.transcribe(_audio(tmp))
        # THEN the tokens are joined into a single transcript
        self.assertEqual(transcript, "Bonjour monde")

    def test_authentication_failure_raises_without_leaking_key(self) -> None:
        # GIVEN a 401 authentication response
        provider = _provider(_transport(401, "unauthorized"))
        with TemporaryDirectory() as tmp:
            # WHEN the audio is transcribed
            with self.assertRaises(GradiumSttError) as ctx:
                provider.transcribe(_audio(tmp))
        # THEN the error is explicit and never contains the API key
        self.assertIn("401", str(ctx.exception))
        self.assertNotIn(API_KEY, str(ctx.exception))

    def test_credit_exhaustion_is_reported(self) -> None:
        # GIVEN a response body mentioning credits
        provider = _provider(_transport(402, "Insufficient credits remaining"))
        with TemporaryDirectory() as tmp:
            # WHEN the audio is transcribed
            with self.assertRaises(GradiumSttError) as ctx:
                provider.transcribe(_audio(tmp))
        # THEN the credit exhaustion is surfaced
        self.assertIn("credits", str(ctx.exception).lower())

    def test_no_recognized_speech_raises_no_speech_detected(self) -> None:
        # GIVEN a 200 response with no text tokens
        provider = _provider(_transport(200, '{"type": "meta", "text": ""}'))
        with TemporaryDirectory() as tmp:
            # WHEN the audio is transcribed
            with self.assertRaises(NoSpeechDetectedError) as ctx:
                provider.transcribe(_audio(tmp))
        # THEN no invented transcript is returned and it is not a generic error
        self.assertIn("no speech", str(ctx.exception).lower())
        self.assertNotIsInstance(ctx.exception, GradiumSttError)

    def test_missing_api_key_is_rejected(self) -> None:
        # GIVEN no API key
        # WHEN a provider is constructed
        # THEN construction fails fast
        with self.assertRaises(ValueError):
            GradiumSttProvider("")

    def test_pcm_input_sends_audio_pcm_content_type(self) -> None:
        # GIVEN a PCM provider and a captured transport
        captured: dict = {}
        body = '{"type": "text", "text": "ok"}'
        provider = GradiumSttProvider(API_KEY, input_format="pcm_16000", transport=_transport(200, body, captured))
        with TemporaryDirectory() as tmp:
            # WHEN the audio is transcribed
            provider.transcribe(_audio(tmp))
        # THEN the Content-Type Gradium accepts for PCM is used (regression: not form-urlencoded)
        self.assertEqual(captured["headers"]["Content-Type"], "audio/pcm")

    def test_ulaw_input_sends_audio_basic_content_type(self) -> None:
        # GIVEN a u-law telephony provider and a captured transport
        captured: dict = {}
        body = '{"type": "text", "text": "ok"}'
        provider = GradiumSttProvider(API_KEY, input_format="ulaw_8000", transport=_transport(200, body, captured))
        with TemporaryDirectory() as tmp:
            # WHEN the audio is transcribed
            provider.transcribe(_audio(tmp))
        # THEN the u-law content type is used
        self.assertEqual(captured["headers"]["Content-Type"], "audio/basic")


class GradiumRunnerIntegrationTest(unittest.TestCase):
    def test_timeout_maps_to_stt_timeout_outcome(self) -> None:
        # GIVEN a transport that times out
        def transport(url, headers, params, content, timeout):
            raise TimeoutError("Gradium STT request timed out")

        runner = SttValidationRunner(_provider(transport), TelemetryRecorder())
        with TemporaryDirectory() as tmp:
            # WHEN the runner validates the audio
            result = runner.validate(_audio(tmp), "corr-timeout")
        # THEN the outcome is a sanitized timeout failure
        self.assertIs(result.outcome, SttOutcome.FAILED)
        self.assertEqual(result.error_code, "stt_timeout")

    def test_api_key_never_appears_in_telemetry_after_failure(self) -> None:
        # GIVEN an auth failure and a telemetry recorder
        telemetry = TelemetryRecorder()
        runner = SttValidationRunner(_provider(_transport(401, "unauthorized")), telemetry)
        with TemporaryDirectory() as tmp:
            # WHEN the runner validates the audio
            result = runner.validate(_audio(tmp), "corr-auth")
        # THEN nothing recorded anywhere contains the API key
        dump = json.dumps(
            {
                "events": [e.attributes for e in telemetry.events()],
                "spans": [s.attributes for s in telemetry.spans()],
                "metrics": [m.attributes for m in telemetry.metrics()],
                "logs": [{"msg": lg.message, "attrs": lg.attributes} for lg in telemetry.logs()],
            },
            default=str,
        )
        self.assertIs(result.outcome, SttOutcome.FAILED)
        self.assertNotIn(API_KEY, dump)
        self.assertEqual(result.error_code, "stt_error")

    def test_no_speech_maps_to_unavailable_not_failed(self) -> None:
        # GIVEN a 200 response that carries no speech tokens
        telemetry = TelemetryRecorder()
        runner = SttValidationRunner(_provider(_transport(200, '{"type": "meta", "text": ""}')), telemetry)
        with TemporaryDirectory() as tmp:
            # WHEN the runner validates the audio
            result = runner.validate(_audio(tmp), "corr-silence")
        # THEN it is reported as UNAVAILABLE with a stable code and no invented transcript
        self.assertIs(result.outcome, SttOutcome.UNAVAILABLE)
        self.assertEqual(result.transcript, "")
        self.assertEqual(result.error_code, "no_speech")
        event_names = [event.name for event in telemetry.events()]
        self.assertIn("stt.unavailable", event_names)
        self.assertNotIn("stt.failure", event_names)
        self.assertEqual(telemetry.logs()[0].level, "info")


class ProviderFactoryTest(unittest.TestCase):
    def test_fixture_provider_is_default(self) -> None:
        # GIVEN the default provider name
        # WHEN a provider is built
        provider = build_provider()
        # THEN the deterministic fixture provider is returned
        self.assertEqual(provider.name, "fixture-stt")

    def test_unknown_provider_is_rejected(self) -> None:
        # GIVEN an unsupported provider name
        # WHEN a provider is built
        # THEN it fails fast
        with self.assertRaises(ValueError):
            build_provider("whisper")


if __name__ == "__main__":
    unittest.main()
