import json
import sys
import threading
import unittest
import urllib.request
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stt_validation import SttOutcome, TelemetryRecorder  # noqa: E402
from web_voice import ChannelEnvelope, WebVoiceIngress  # noqa: E402
from web_voice.envelope import WEB_VOICE_CHANNEL  # noqa: E402
from web_voice.server import (  # noqa: E402
    STT_ROUTE,
    WebVoiceHTTPServer,
    _envelope_from_query,
    build_handler,
)

SECRET_PATH = "/private/customer/invoice-4213.pcm"


class _StubProvider:
    """In-memory STT provider so ingress tests never touch the network."""

    name = "stub-stt"

    def __init__(self, transcript: str = "bonjour je paye trop cher", error: Exception | None = None) -> None:
        self._transcript = transcript
        self._error = error
        self.received_paths: list[Path] = []
        self.path_existed_during_call: bool | None = None
        self.audio_bytes_seen: int | None = None

    def transcribe(self, audio_path: Path) -> str:
        self.received_paths.append(audio_path)
        self.path_existed_during_call = audio_path.exists()
        self.audio_bytes_seen = len(audio_path.read_bytes())
        if self._error is not None:
            raise self._error
        return self._transcript


def _span(telemetry: TelemetryRecorder, name: str):
    return next(span for span in telemetry.spans() if span.name == name)


class WebVoiceIngressTest(unittest.TestCase):
    def test_successful_turn_returns_transcript(self) -> None:
        provider = _StubProvider(transcript="bonjour")
        ingress = WebVoiceIngress(provider)
        telemetry = TelemetryRecorder()

        result = ingress.transcribe_turn(b"\x01\x02\x03\x04", ChannelEnvelope.for_web_turn(), telemetry)

        self.assertEqual(result.outcome, SttOutcome.SUCCESS)
        self.assertEqual(result.transcript, "bonjour")
        self.assertEqual(provider.audio_bytes_seen, 4)

    def test_ingress_span_reports_real_audio_bytes(self) -> None:
        # RF-002: a real channel-ingress measurement, not a path.exists() analog.
        ingress = WebVoiceIngress(_StubProvider())
        telemetry = TelemetryRecorder()
        audio = b"\x00" * 640

        ingress.transcribe_turn(audio, ChannelEnvelope.for_web_turn(), telemetry)

        span = _span(telemetry, "web.voice.ingress")
        self.assertEqual(span.attributes["audio_bytes"], 640)
        self.assertEqual(span.attributes["channel"], WEB_VOICE_CHANNEL)
        self.assertEqual(span.attributes["audio_format"], "pcm_16000")

    def test_ingress_span_uses_transport_receive_duration(self) -> None:
        # The server measures the real time reading audio off the wire and passes
        # it in; the ingress span duration must reflect that, not a local no-op.
        ingress = WebVoiceIngress(_StubProvider())
        telemetry = TelemetryRecorder()

        ingress.transcribe_turn(b"\x01\x02", ChannelEnvelope.for_web_turn(), telemetry, received_ms=12.5)

        self.assertEqual(_span(telemetry, "web.voice.ingress").duration_ms, 12.5)

    def test_correlation_id_is_propagated_end_to_end(self) -> None:
        ingress = WebVoiceIngress(_StubProvider())
        telemetry = TelemetryRecorder()
        envelope = ChannelEnvelope.for_web_turn(correlation_id="corr-web-1")

        result = ingress.transcribe_turn(b"\x01\x02", envelope, telemetry)

        self.assertEqual(result.correlation_id, "corr-web-1")
        self.assertEqual(_span(telemetry, "web.voice.ingress").attributes["correlation_id"], "corr-web-1")
        self.assertEqual(_span(telemetry, "stt.request").attributes["correlation_id"], "corr-web-1")

    def test_failure_is_sanitized_and_never_leaks_paths(self) -> None:
        provider = _StubProvider(error=FileNotFoundError(f"missing {SECRET_PATH}"))
        ingress = WebVoiceIngress(provider)

        result = ingress.transcribe_turn(b"\x01", ChannelEnvelope.for_web_turn())

        self.assertEqual(result.outcome, SttOutcome.FAILED)
        self.assertEqual(result.error_code, "fixture_missing")
        self.assertNotIn(SECRET_PATH, result.error_reason or "")
        self.assertIn("<redacted-path>", result.error_reason or "")

    def test_temp_audio_file_is_cleaned_up(self) -> None:
        provider = _StubProvider()
        ingress = WebVoiceIngress(provider)

        ingress.transcribe_turn(b"\x01\x02\x03", ChannelEnvelope.for_web_turn())

        self.assertTrue(provider.path_existed_during_call)
        self.assertFalse(provider.received_paths[0].exists())


class EnvelopeFromQueryTest(unittest.TestCase):
    def test_uses_provided_ids(self) -> None:
        envelope = _envelope_from_query("conversation_id=c1&session_id=s1&correlation_id=k1")
        self.assertEqual(envelope.conversation_id, "c1")
        self.assertEqual(envelope.external_session_id, "s1")
        self.assertEqual(envelope.correlation_id, "k1")
        self.assertEqual(envelope.channel, WEB_VOICE_CHANNEL)

    def test_generates_ids_when_absent(self) -> None:
        envelope = _envelope_from_query("")
        self.assertTrue(envelope.conversation_id)
        self.assertTrue(envelope.correlation_id)


class WebVoiceServerTest(unittest.TestCase):
    def _serve(self, ingress: WebVoiceIngress) -> tuple[WebVoiceHTTPServer, int]:
        server = WebVoiceHTTPServer(("127.0.0.1", 0), build_handler(ingress))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, server.server_address[1]

    def _post(self, port: int, body: bytes, path: str = STT_ROUTE):
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", path, body=body, headers={"Content-Type": "audio/pcm"})
        response = conn.getresponse()
        payload = response.read().decode("utf-8")
        conn.close()
        return response.status, payload

    def test_post_success_returns_transcript_json(self) -> None:
        _, port = self._serve(WebVoiceIngress(_StubProvider(transcript="bonjour")))

        status, payload = self._post(port, b"\x01\x02\x03\x04")

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["transcript"], "bonjour")

    def test_post_failure_maps_to_http_502(self) -> None:
        _, port = self._serve(WebVoiceIngress(_StubProvider(error=ValueError("bad audio"))))

        status, payload = self._post(port, b"\x01")

        self.assertEqual(status, 502)
        self.assertEqual(json.loads(payload)["outcome"], "failed")

    def test_unknown_route_returns_404(self) -> None:
        _, port = self._serve(WebVoiceIngress(_StubProvider()))

        status, _payload = self._post(port, b"\x01", path="/api/voice/unknown")

        self.assertEqual(status, 404)

    def test_index_page_is_served(self) -> None:
        _, port = self._serve(WebVoiceIngress(_StubProvider()))

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
            body = resp.read().decode("utf-8")

        self.assertIn("Web Voice Chat", body)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
