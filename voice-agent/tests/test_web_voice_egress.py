import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tts_synthesis import FixtureTtsProvider, TtsOutcome  # noqa: E402
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice import (  # noqa: E402
    CHANNEL_EGRESS_SPAN,
    ChannelEnvelope,
    WebVoiceEgress,
    WebVoiceIngress,
    pcm_to_wav,
)
from web_voice.runtime import StdlibTurnProcessor  # noqa: E402
from web_voice.server import (  # noqa: E402
    TTS_ROUTE,
    WebVoiceHTTPServer,
    build_handler,
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


class WebVoiceTtsServerTest(unittest.TestCase):
    def _serve(self) -> int:
        ingress = WebVoiceIngress(_StubStt())
        egress = WebVoiceEgress(FixtureTtsProvider())
        processor = StdlibTurnProcessor(ingress, egress)
        server = WebVoiceHTTPServer(("127.0.0.1", 0), build_handler(processor))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def _post(self, port: int, query: dict) -> tuple[int, str, bytes]:
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", f"{TTS_ROUTE}?{urlencode(query)}")
        response = conn.getresponse()
        body = response.read()
        content_type = response.getheader("Content-Type", "")
        conn.close()
        return response.status, content_type, body

    def test_post_text_returns_playable_wav(self) -> None:
        port = self._serve()

        status, content_type, body = self._post(port, {"text": "Bonjour", "correlation_id": "c1"})

        self.assertEqual(status, 200)
        self.assertEqual(content_type, "audio/wav")
        self.assertEqual(body[:4], b"RIFF")

    def test_post_empty_text_returns_sanitized_json_error(self) -> None:
        port = self._serve()

        status, content_type, body = self._post(port, {"text": ""})

        self.assertEqual(status, 502)
        self.assertIn("application/json", content_type)
        self.assertEqual(json.loads(body.decode("utf-8"))["outcome"], "unavailable")


class _StubStt:
    name = "stub-stt"

    def transcribe(self, audio_path: Path) -> str:
        return "bonjour"


if __name__ == "__main__":
    unittest.main()
