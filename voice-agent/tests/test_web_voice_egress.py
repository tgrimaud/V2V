import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tts_synthesis import FixtureTtsProvider, TtsOutcome  # noqa: E402
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice import (  # noqa: E402
    CHANNEL_EGRESS_SPAN,
    ChannelEnvelope,
    WebVoiceEgress,
    pcm_to_wav,
)


class _RaisingProvider:
    name = "boom-tts"
    audio_format = "pcm_16000"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def synthesize(self, text: str) -> bytes:
        raise self._exc


def _envelope() -> ChannelEnvelope:
    return ChannelEnvelope.for_web_turn(correlation_id="corr-egress")


def _span(telemetry: TelemetryRecorder, name: str):
    return next((s for s in telemetry.spans() if s.name == name), None)


class PcmToWavTest(unittest.TestCase):
    def test_wraps_pcm_with_a_44_byte_riff_wave_header(self) -> None:
        # GIVEN 4 bytes of PCM
        wav = pcm_to_wav(b"\x01\x02\x03\x04", sample_rate=16000)

        # THEN a valid RIFF/WAVE/data header precedes the payload
        self.assertEqual(wav[:4], b"RIFF")
        self.assertEqual(wav[8:12], b"WAVE")
        self.assertEqual(wav[36:40], b"data")
        self.assertEqual(len(wav), 44 + 4)
        self.assertEqual(wav[44:], b"\x01\x02\x03\x04")


class WebVoiceEgressTest(unittest.TestCase):
    def test_success_returns_wav_and_emits_egress_span(self) -> None:
        # GIVEN the deterministic fixture TTS provider
        egress = WebVoiceEgress(FixtureTtsProvider())
        telemetry = TelemetryRecorder()

        # WHEN a turn is synthesized and reported sent
        response = egress.synthesize_turn("Bonjour le monde", _envelope(), telemetry)
        egress.record_egress(response, _envelope(), telemetry, sent_ms=2.5)

        # THEN a playable WAV is produced and the egress slice span is emitted
        self.assertIs(response.result.outcome, TtsOutcome.SUCCESS)
        self.assertIsNotNone(response.wav)
        self.assertEqual(response.wav[:4], b"RIFF")
        span = _span(telemetry, CHANNEL_EGRESS_SPAN)
        self.assertIsNotNone(span)
        self.assertEqual(span.attributes["audio_bytes"], len(response.wav))
        self.assertEqual(span.attributes["correlation_id"], "corr-egress")

    def test_empty_text_is_unavailable_with_no_wav_and_no_egress_span(self) -> None:
        # GIVEN whitespace-only text
        egress = WebVoiceEgress(FixtureTtsProvider())
        telemetry = TelemetryRecorder()

        # WHEN synthesized
        response = egress.synthesize_turn("   ", _envelope(), telemetry)
        egress.record_egress(response, _envelope(), telemetry)  # no-op

        # THEN no audio is invented and the egress slice stays unmeasured
        self.assertIs(response.result.outcome, TtsOutcome.UNAVAILABLE)
        self.assertIsNone(response.wav)
        self.assertIsNone(_span(telemetry, CHANNEL_EGRESS_SPAN))

    def test_provider_failure_is_failed_with_no_wav(self) -> None:
        # GIVEN a provider that raises
        egress = WebVoiceEgress(_RaisingProvider(RuntimeError("Gradium TTS credits exhausted")))
        telemetry = TelemetryRecorder()

        # WHEN synthesized
        response = egress.synthesize_turn("Bonjour", _envelope(), telemetry)

        # THEN it is FAILED, no WAV, sanitized error code exposed
        self.assertIs(response.result.outcome, TtsOutcome.FAILED)
        self.assertIsNone(response.wav)
        self.assertEqual(response.result.error_code, "tts_error")


# The HTTP-surface TTS behaviour (playable WAV, empty-text 502, provider-failure client-safe
# body) is covered by the aiohttp parity suite (`tests/test_web_voice_app.py`). The stdlib
# `WebVoiceHTTPServer` TTS server tests were retired with the stdlib server itself
# (ADR-0053 / TASK-WEB-048 Phase 2).


if __name__ == "__main__":
    unittest.main()
