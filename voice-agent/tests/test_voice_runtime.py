"""Tests for the voice runtime seam (TASK-WEB-005, ST-6).

The `/api/voice/turn` HTTP-surface behaviour (base64 WAV body, chunked→411, degraded,
STT-fail 502 client-safe shape, cross-runtime parity, server-log) and the WebRTC offer
backpressure (503 + Retry-After, 502 no-leak) are covered by the aiohttp parity suite
`tests/test_web_voice_app.py`. The stdlib `WebVoiceHTTPServer` endpoint tests were retired
with the stdlib server itself (ADR-0053 / TASK-WEB-048 Phase 2). This module keeps the
transport-agnostic `VoiceTurnProcessor` seam tests (no HTTP server).
"""

import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
