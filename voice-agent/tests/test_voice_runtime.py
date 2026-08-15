"""Tests for the voice runtime seam + /api/voice/turn endpoint (TASK-WEB-005, ST-6)."""

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation_backend import (  # noqa: E402
    DEGRADED_FALLBACK_TEXT,
    AnswerOutcome,
    AnswerRequest,
    AnswerResult,
    StubBackendAdapter,
)
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
from web_voice.error_response import SessionCapacityError  # noqa: E402
from web_voice.server import (  # noqa: E402
    TURN_ROUTE,
    WEBRTC_OFFER_ROUTE,
    WebVoiceHTTPServer,
    build_handler,
)


class _FakeBackend:
    """Answers with a marker prefix so tests can prove the answer is spoken, not the transcript."""

    name = "fake-backend"

    def answer(self, request: AnswerRequest) -> AnswerResult:
        return AnswerResult(
            text="ANSWER:" + request.transcript,
            provider=self.name,
            outcome=AnswerOutcome.SUCCESS,
            correlation_id=request.correlation_id,
        )


class _UnavailableBackend:
    """Backend that always fails, to exercise the degraded (safe fallback) path."""

    name = "unavailable-backend"

    def answer(self, request: AnswerRequest) -> AnswerResult:
        raise RuntimeError("backend endpoint unreachable")


class _CapturingEgress:
    """Wraps the fixture egress and records the text handed to TTS."""

    def __init__(self) -> None:
        self._egress = WebVoiceEgress(FixtureTtsProvider())
        self.texts: list[str] = []

    def synthesize_turn(self, text, envelope, telemetry=None):
        self.texts.append(text)
        return self._egress.synthesize_turn(text, envelope, telemetry)

    def record_egress(self, response, envelope, telemetry, *, sent_ms=None) -> None:
        self._egress.record_egress(response, envelope, telemetry, sent_ms=sent_ms)


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

    def test_both_runtimes_speak_the_backend_answer_not_the_transcript(self) -> None:
        # GIVEN both runtimes wired to the same fake backend + a capturing egress
        envelope = ChannelEnvelope.for_web_turn(correlation_id="corr-answer")
        for runtime_cls in (StdlibTurnProcessor, PipecatTurnProcessor):
            with self.subTest(runtime=runtime_cls.__name__):
                egress = _CapturingEgress()
                processor = runtime_cls(_ingress(), egress, _FakeBackend())
                # WHEN a full turn runs (stub STT transcribes "bonjour")
                result = processor.run_turn(b"\x01\x02" * 100, envelope)
                # THEN the backend answer (not the transcript) is what was synthesized
                self.assertEqual(result.answer_result.text, "ANSWER:bonjour")
                self.assertEqual(egress.texts, ["ANSWER:bonjour"])
                self.assertNotIn("bonjour", [t for t in egress.texts if t == "bonjour"])

    def test_both_runtimes_speak_the_safe_fallback_when_the_backend_fails(self) -> None:
        # GIVEN both runtimes wired to a backend that is unavailable
        envelope = ChannelEnvelope.for_web_turn(correlation_id="corr-degraded")
        for runtime_cls in (StdlibTurnProcessor, PipecatTurnProcessor):
            with self.subTest(runtime=runtime_cls.__name__):
                egress = _CapturingEgress()
                processor = runtime_cls(_ingress(), egress, _UnavailableBackend())
                # WHEN a full turn runs
                result = processor.run_turn(b"\x01\x02" * 100, envelope)
                # THEN the safe fallback (degraded) is synthesized, not a failed/empty turn
                self.assertIs(result.answer_result.outcome, AnswerOutcome.DEGRADED)
                self.assertEqual(result.answer_result.text, DEGRADED_FALLBACK_TEXT)
                self.assertEqual(egress.texts, [DEGRADED_FALLBACK_TEXT])
                self.assertIs(result.tts_response.result.outcome, TtsOutcome.SUCCESS)
                self.assertTrue(result.audio)

    def test_default_backend_is_the_stub(self) -> None:
        # GIVEN a processor built without an explicit backend
        processor = build_turn_processor(STDLIB, _ingress(), _egress())
        envelope = ChannelEnvelope.for_web_turn(correlation_id="corr-default")
        # WHEN a full turn runs
        result = processor.run_turn(b"\x01\x02" * 100, envelope)
        # THEN the deterministic stub answered
        self.assertEqual(result.answer_result.provider, StubBackendAdapter().name)
        self.assertIs(result.answer_result.outcome, AnswerOutcome.SUCCESS)


class VoiceTurnEndpointTest(unittest.TestCase):
    def _serve(self, runtime: str, ingress: WebVoiceIngress | None = None, backend=None) -> int:
        processor = build_turn_processor(runtime, ingress or _ingress(), _egress(), backend)
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

    def test_turn_endpoint_exposes_transcript_and_answer_headers(self) -> None:
        # GIVEN the server on the pipecat runtime (stub STT transcribes "bonjour")
        port = self._serve(PIPECAT)
        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("POST", TURN_ROUTE, body=b"\x01\x02" * 200)
        response = conn.getresponse()
        response.read()
        # WHEN the reply headers are read
        transcript = unquote(response.getheader("X-Voice-Transcript") or "")
        answer = unquote(response.getheader("X-Voice-Answer") or "")
        provider = response.getheader("X-Answer-Provider")
        correlation = response.getheader("X-Correlation-Id")
        conn.close()
        # THEN the transcript, spoken answer and provider are exposed to the client
        self.assertEqual(transcript, "bonjour")
        self.assertTrue(answer)
        self.assertNotEqual(answer, transcript)  # the reply is the answer, not an echo
        self.assertEqual(provider, "stub-backend")
        self.assertTrue(correlation)

    def test_turn_endpoint_rejects_a_chunked_body_with_411(self) -> None:
        # GIVEN the server on the pipecat runtime
        port = self._serve(PIPECAT)
        conn = HTTPConnection("127.0.0.1", port, timeout=10)

        # WHEN a body is streamed with no Content-Length (http.client uses Transfer-Encoding:
        # chunked for a generator body) — which _read_body would otherwise read as an empty turn
        def _chunks():
            yield b"\x01\x02" * 50

        conn.request("POST", TURN_ROUTE, body=_chunks())
        response = conn.getresponse()
        payload = response.read()
        conn.close()
        # THEN the server asks for a Content-Length (411) instead of silently treating it as empty
        self.assertEqual(response.status, 411)
        self.assertIn(b"length_required", payload)

    def test_turn_endpoint_speaks_a_degraded_wav_when_the_backend_fails(self) -> None:
        # GIVEN both runtimes wired to an unavailable backend (STT still succeeds)
        for runtime in (STDLIB, PIPECAT):
            with self.subTest(runtime=runtime):
                port = self._serve(runtime, backend=_UnavailableBackend())
                conn = HTTPConnection("127.0.0.1", port, timeout=10)
                conn.request("POST", TURN_ROUTE, body=b"\x01\x02" * 200)
                response = conn.getresponse()
                payload = response.read()
                outcome = response.getheader("X-Answer-Outcome")
                reason = response.getheader("X-Answer-Degraded-Reason")
                answer = unquote(response.getheader("X-Voice-Answer") or "")
                conn.close()
                # THEN the turn still returns a spoken WAV (never a 502) flagged degraded
                self.assertEqual(response.status, 200)
                self.assertEqual(payload[:4], b"RIFF")
                self.assertEqual(outcome, "degraded")
                self.assertEqual(reason, "backend_unavailable")
                self.assertEqual(answer, DEGRADED_FALLBACK_TEXT)

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

    def test_turn_502_body_is_client_safe_on_both_runtimes(self) -> None:
        # GIVEN both runtimes wired to an STT provider that raises a distinctive message
        # (_FailingStt raises RuntimeError("provider unavailable"))
        for runtime in (STDLIB, PIPECAT):
            with self.subTest(runtime=runtime):
                port = self._serve(runtime, _failing_ingress())
                # WHEN a phrase is posted and a 502 is returned
                status, _content_type, payload = self._post_turn(port, b"\x01\x02" * 200)
                self.assertEqual(status, 502)
                body = json.loads(payload)
                # THEN the body carries a stable error_code, correlation id and a
                # generic message — and NEVER the raw provider exception text (RF-013)
                self.assertTrue(body["error_code"])
                self.assertTrue(body["correlation_id"])
                self.assertTrue(body["message"])
                self.assertNotIn("error_reason", body)
                self.assertNotIn("provider unavailable", payload.decode("utf-8"))

    def test_both_runtimes_return_the_identical_client_safe_error_shape(self) -> None:
        # GIVEN both runtimes failing at the STT slice
        stdlib_body = self._error_body(self._serve(STDLIB, _failing_ingress()))
        pipecat_body = self._error_body(self._serve(PIPECAT, _failing_ingress()))
        # THEN the client-safe error contract is identical modulo the correlation id
        for body in (stdlib_body, pipecat_body):
            body.pop("correlation_id")
        self.assertEqual(stdlib_body, pipecat_body)

    def test_turn_502_keeps_the_full_reason_in_the_server_log(self) -> None:
        # GIVEN a failing STT and a captured server stderr (structured turn log)
        import io

        port = self._serve(STDLIB, _failing_ingress())
        captured = io.StringIO()
        original_stderr = sys.stderr
        sys.stderr = captured
        try:
            # WHEN a turn fails (the handler logs the turn before sending the 502)
            _status, _content_type, payload = self._post_turn(port, b"\x01\x02" * 200)
        finally:
            sys.stderr = original_stderr
        # THEN the raw reason is absent from the client body but present server-side
        self.assertNotIn("provider unavailable", payload.decode("utf-8"))
        self.assertIn("provider unavailable", captured.getvalue())

    def _error_body(self, port: int) -> dict:
        _status, _content_type, payload = self._post_turn(port, b"\x01\x02" * 200)
        return json.loads(payload)


class PipecatBatchLoopReuseTest(unittest.TestCase):
    """TASK-WEB-024: the batch pipecat path reuses one background loop across turns
    instead of creating and tearing down an event loop per HTTP turn (asyncio.run)."""

    def test_reuses_one_background_loop_across_turns_then_closes_it(self) -> None:
        processor = PipecatTurnProcessor(_ingress(), _egress())
        envelope = ChannelEnvelope.for_web_turn(correlation_id="c")
        # GIVEN a fresh processor -> the loop is created lazily (none until the first turn)
        self.assertIsNone(processor._loop)
        # WHEN two turns run
        processor.run_turn(b"\x01\x02" * 100, envelope)
        first_loop = processor._loop
        self.assertIsNotNone(first_loop)
        processor.run_turn(b"\x01\x02" * 100, envelope)
        # THEN the same loop instance served both turns (not recreated per turn)
        self.assertIs(processor._loop, first_loop)
        # AND close() stops the loop it owns
        processor.close()
        self.assertIsNone(processor._loop)

    def test_injected_loop_is_reused_and_left_open_for_its_owner(self) -> None:
        from web_voice.async_loop import BackgroundEventLoop

        loop = BackgroundEventLoop()
        loop.start()
        try:
            processor = PipecatTurnProcessor(_ingress(), _egress(), loop=loop)
            envelope = ChannelEnvelope.for_web_turn(correlation_id="c")
            processor.run_turn(b"\x01\x02" * 100, envelope)
            self.assertIs(processor._loop, loop)
            # WHEN the processor is closed -> it does NOT stop a caller-owned loop
            processor.close()
            self.assertIs(processor._loop, loop)
            # AND the loop is still usable afterwards
            result = processor.run_turn(b"\x01\x02" * 100, envelope)
            self.assertIs(result.transcript_result.outcome, SttOutcome.SUCCESS)
        finally:
            loop.stop()


class WebRtcOfferBackpressureTest(unittest.TestCase):
    """TASK-WEB-024: the offer endpoint answers 503 (+ Retry-After) when the signaling
    layer refuses on the concurrency cap, and stays 502 for any other negotiation error."""

    def _serve(self, signaling) -> int:
        # The offer route does not use the turn processor, so a placeholder is enough.
        server = WebVoiceHTTPServer(("127.0.0.1", 0), build_handler(object(), signaling))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def _post_offer(self, port: int):
        conn = HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("POST", WEBRTC_OFFER_ROUTE, body=b"{}")
        response = conn.getresponse()
        payload = response.read()
        retry_after = response.getheader("Retry-After")
        conn.close()
        return response.status, retry_after, payload

    def test_capacity_rejection_returns_503_with_retry_after(self) -> None:
        class _FullSignaling:
            def handle_offer(self, offer, **kwargs):
                raise SessionCapacityError(8, 8)

        # GIVEN a signaling layer at capacity
        port = self._serve(_FullSignaling())
        # WHEN a WebRTC offer is posted
        status, retry_after, payload = self._post_offer(port)
        # THEN the client gets a clean 503 + Retry-After with the active/max counts
        self.assertEqual(status, 503)
        self.assertEqual(retry_after, "5")
        body = json.loads(payload)
        self.assertEqual(body["error"], "capacity")
        self.assertEqual(body["active"], 8)
        self.assertEqual(body["max"], 8)

    def test_other_negotiation_error_stays_502_and_leaks_no_detail(self) -> None:
        class _BoomSignaling:
            def handle_offer(self, offer, **kwargs):
                raise RuntimeError("raw sdp negotiation boom")

        # GIVEN a signaling layer that fails for a non-capacity reason
        port = self._serve(_BoomSignaling())
        status, _retry_after, payload = self._post_offer(port)
        # THEN it is a generic 502 that never echoes the raw exception text
        self.assertEqual(status, 502)
        self.assertEqual(json.loads(payload)["error"], "webrtc_negotiation_failed")
        self.assertNotIn("boom", payload.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
