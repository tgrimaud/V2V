"""Tests for the voice runtime seam + /api/voice/turn endpoint (TASK-WEB-005, ST-6)."""

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stt_validation.models import SttOutcome  # noqa: E402
from tts_synthesis import FixtureTtsProvider, TtsOutcome  # noqa: E402
from web_voice import ChannelEnvelope, WebVoiceEgress, WebVoiceIngress  # noqa: E402
from web_voice.runtime import (  # noqa: E402
    PIPECAT,
    STDLIB,
    PipecatTurnProcessor,
    StdlibTurnProcessor,
    build_turn_processor,
)
from web_voice.server import TURN_ROUTE, WebVoiceHTTPServer, build_handler  # noqa: E402


class _StubStt:
    name = "stub-stt"

    def transcribe(self, audio_path) -> str:  # noqa: ANN001
        return "bonjour"


class _FailingStt:
    """STT provider that raises so the runner yields a non-SUCCESS outcome."""

    name = "failing-stt"

    def transcribe(self, audio_path) -> str:  # noqa: ANN001
        raise RuntimeError("provider unavailable")


def _ingress() -> WebVoiceIngress:
    return WebVoiceIngress(_StubStt())


def _failing_ingress() -> WebVoiceIngress:
    return WebVoiceIngress(_FailingStt())


def _egress() -> WebVoiceEgress:
    return WebVoiceEgress(FixtureTtsProvider())


class BuildTurnProcessorTest(unittest.TestCase):
    def test_returns_the_selected_runtime_implementation(self) -> None:
        # GIVEN each known runtime name
        # WHEN a processor is built
        # THEN the matching implementation is returned
        self.assertIsInstance(build_turn_processor(STDLIB, _ingress(), _egress()), StdlibTurnProcessor)
        self.assertIsInstance(build_turn_processor(PIPECAT, _ingress(), _egress()), PipecatTurnProcessor)

    def test_rejects_an_unknown_runtime(self) -> None:
        # GIVEN an unknown runtime name
        # WHEN a processor is built
        # THEN it fails fast
        with self.assertRaises(ValueError):
            build_turn_processor("bogus", _ingress(), _egress())


class TurnProcessorParityTest(unittest.TestCase):
    def test_both_runtimes_run_the_full_turn_successfully(self) -> None:
        # GIVEN both runtimes wired to the same stub STT + fixture TTS
        stdlib = StdlibTurnProcessor(_ingress(), _egress())
        pipecat = PipecatTurnProcessor(_ingress(), _egress())
        envelope = ChannelEnvelope.for_web_turn(correlation_id="corr-turn")
        # WHEN each runs a full turn on the same audio
        stdlib_result = stdlib.run_turn(b"\x01\x02" * 100, envelope)
        pipecat_result = pipecat.run_turn(b"\x01\x02" * 100, envelope)
        # THEN both transcribe, synthesize and produce identical audio
        self.assertIs(stdlib_result.transcript_result.outcome, SttOutcome.SUCCESS)
        self.assertIs(pipecat_result.transcript_result.outcome, SttOutcome.SUCCESS)
        self.assertIs(stdlib_result.tts_response.result.outcome, TtsOutcome.SUCCESS)
        self.assertEqual(stdlib_result.audio, pipecat_result.audio)
        self.assertTrue(stdlib_result.audio)


class VoiceTurnEndpointTest(unittest.TestCase):
    def _serve(self, runtime: str, ingress: WebVoiceIngress | None = None) -> int:
        processor = build_turn_processor(runtime, ingress or _ingress(), _egress())
        server = WebVoiceHTTPServer(("127.0.0.1", 0), build_handler(processor))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def _post_turn(self, port: int, body: bytes):
        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("POST", TURN_ROUTE, body=body)
        response = conn.getresponse()
        payload = response.read()
        content_type = response.getheader("Content-Type")
        conn.close()
        return response.status, content_type, payload

    def test_turn_endpoint_returns_wav_on_pipecat_runtime(self) -> None:
        # GIVEN the server on the pipecat runtime
        port = self._serve(PIPECAT)
        # WHEN a phrase is posted to the full-pipeline endpoint
        status, content_type, payload = self._post_turn(port, b"\x01\x02" * 200)
        # THEN a playable WAV is returned
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "audio/wav")
        self.assertEqual(payload[:4], b"RIFF")
        self.assertEqual(payload[8:12], b"WAVE")

    def test_turn_endpoint_returns_identical_wav_across_runtimes(self) -> None:
        # GIVEN the server on each runtime
        stdlib_port = self._serve(STDLIB)
        pipecat_port = self._serve(PIPECAT)
        # WHEN the same phrase is posted to each
        _s1, _c1, stdlib_wav = self._post_turn(stdlib_port, b"\x03\x04" * 200)
        _s2, _c2, pipecat_wav = self._post_turn(pipecat_port, b"\x03\x04" * 200)
        # THEN both runtimes produce byte-identical audio
        self.assertEqual(stdlib_wav, pipecat_wav)

    def test_turn_endpoint_fails_closed_with_json_when_stt_fails(self) -> None:
        # GIVEN both runtimes wired to an STT provider that fails
        for runtime in (STDLIB, PIPECAT):
            with self.subTest(runtime=runtime):
                port = self._serve(runtime, _failing_ingress())
                # WHEN a phrase is posted to the full-pipeline endpoint
                status, content_type, payload = self._post_turn(port, b"\x01\x02" * 200)
                # THEN the turn fails closed: a 502 JSON error, never a WAV
                self.assertEqual(status, 502)
                self.assertEqual(content_type, "application/json")
                self.assertNotEqual(payload[:4], b"RIFF")
                # AND the failed outcome is carried with a correlation id (observable)
                body = json.loads(payload)
                self.assertEqual(body["outcome"], "failed")
                self.assertTrue(body["correlation_id"])


if __name__ == "__main__":
    unittest.main()
