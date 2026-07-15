"""Tests for the in-memory batch pipeline with the backend answer step
(TASK-WEB-005 ST-4; backend answer wired in TASK-WEB-003-D)."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from conversation_backend import AnswerOutcome, AnswerRequest, AnswerResult, StubBackendAdapter  # noqa: E402
from stt_validation.models import SttOutcome, TranscriptResult  # noqa: E402
from tts_synthesis.models import SynthesisResult, TtsOutcome  # noqa: E402
from voice_pipeline.pipeline import run_batch_turn  # noqa: E402


def _transcript(outcome: SttOutcome, text: str = "") -> TranscriptResult:
    return TranscriptResult(
        transcript=text,
        provider="fake-stt",
        outcome=outcome,
        duration_ms=1.0,
        stt_request_ms=1.0,
        correlation_id="corr-1",
    )


def _envelope() -> SimpleNamespace:
    return SimpleNamespace(
        channel="web_voice",
        conversation_id="conv-1",
        correlation_id="corr-1",
        external_session_id="s",
    )


class _FakeIngress:
    def __init__(self, result: TranscriptResult) -> None:
        self._result = result
        self.calls: list[tuple] = []

    def transcribe_turn(self, audio, envelope, telemetry=None, *, received_ms=None):
        self.calls.append((audio, envelope, telemetry, received_ms))
        return self._result


class _FakeBackend:
    """Prefixes the transcript so tests can prove the answer (not the transcript) is spoken."""

    name = "fake-backend"

    def answer(self, request: AnswerRequest) -> AnswerResult:
        return AnswerResult(
            text="ANSWERED:" + request.transcript,
            provider=self.name,
            outcome=AnswerOutcome.SUCCESS,
            correlation_id=request.correlation_id,
        )


class _FakeEgress:
    """Encodes the spoken text into fake PCM so parity is deterministic."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def synthesize_turn(self, text, envelope, telemetry=None):
        self.calls.append((text, envelope, telemetry))
        result = SynthesisResult(
            audio=b"AUDIO:" + text.encode("utf-8"),
            provider="fake-tts",
            outcome=TtsOutcome.SUCCESS,
            duration_ms=1.0,
            tts_request_ms=1.0,
            correlation_id="corr-1",
            audio_format="pcm_16000",
        )
        return SimpleNamespace(result=result, wav=b"WAV:" + text.encode("utf-8"))


class RunBatchTurnTest(unittest.IsolatedAsyncioTestCase):
    async def test_answers_instead_of_echoing_end_to_end(self) -> None:
        # GIVEN an ingress that transcribes, a backend that answers and an egress to PCM
        ingress = _FakeIngress(_transcript(SttOutcome.SUCCESS, text="hello"))
        egress = _FakeEgress()
        # WHEN a turn runs through the pipeline with the backend wired
        result = await run_batch_turn(b"\x01\x02", _envelope(), ingress=ingress, egress=egress, backend=_FakeBackend())
        # THEN the backend answer (not the transcript) is what gets synthesized
        self.assertEqual(result.transcript_result.transcript, "hello")
        self.assertEqual(result.answer_result.text, "ANSWERED:hello")
        self.assertEqual(egress.calls[0][0], "ANSWERED:hello")
        self.assertNotEqual(egress.calls[0][0], "hello")  # no longer an echo
        self.assertEqual(result.audio, b"AUDIO:ANSWERED:hello")
        self.assertIs(result.tts_response.result.outcome, TtsOutcome.SUCCESS)

    async def test_defaults_to_the_stub_backend_when_none_is_injected(self) -> None:
        # GIVEN a successful transcript and no explicit backend
        ingress = _FakeIngress(_transcript(SttOutcome.SUCCESS, text="hello"))
        egress = _FakeEgress()
        # WHEN a turn runs
        result = await run_batch_turn(b"\x01\x02", _envelope(), ingress=ingress, egress=egress)
        # THEN the deterministic stub answered (default offline backend)
        self.assertEqual(result.answer_result.provider, StubBackendAdapter().name)
        self.assertIs(result.answer_result.outcome, AnswerOutcome.SUCCESS)
        self.assertEqual(egress.calls[0][0], result.answer_result.text)

    async def test_stt_failure_produces_no_audio_and_skips_backend_and_tts(self) -> None:
        # GIVEN an ingress that fails
        ingress = _FakeIngress(_transcript(SttOutcome.FAILED))
        egress = _FakeEgress()
        # WHEN a turn runs
        result = await run_batch_turn(b"\x01", _envelope(), ingress=ingress, egress=egress, backend=_FakeBackend())
        # THEN no transcript flows, neither backend nor TTS run, no audio is produced
        self.assertIs(result.transcript_result.outcome, SttOutcome.FAILED)
        self.assertIsNone(result.answer_result)
        self.assertEqual(egress.calls, [])
        self.assertIsNone(result.tts_response)
        self.assertEqual(result.audio, b"")

    async def test_passes_audio_and_received_ms_to_ingress(self) -> None:
        # GIVEN an ingress and a known audio buffer + received window
        ingress = _FakeIngress(_transcript(SttOutcome.SUCCESS, text="x"))
        egress = _FakeEgress()
        # WHEN a turn runs with a received window
        await run_batch_turn(b"\xaa\xbb", _envelope(), ingress=ingress, egress=egress, received_ms=7.0)
        # THEN the ingress got the exact audio and window
        audio, _env, _tel, received_ms = ingress.calls[0]
        self.assertEqual(audio, b"\xaa\xbb")
        self.assertEqual(received_ms, 7.0)


if __name__ == "__main__":
    unittest.main()
