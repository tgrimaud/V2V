"""Tests for the in-memory batch pipeline with the backend answer step
(TASK-WEB-005 ST-4; backend answer wired in TASK-WEB-003-D)."""

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from conversation_backend import (  # noqa: E402
    CHUNK,
    DONE,
    AnswerOutcome,
    AnswerRequest,
    AnswerResult,
    AnswerStreamEvent,
    StubBackendAdapter,
)
from stt_validation.models import SttOutcome, TranscriptResult  # noqa: E402
from tts_synthesis.models import SynthesisResult, TtsOutcome  # noqa: E402
from voice_pipeline.pipeline import run_batch_turn  # noqa: E402
from web_voice.egress import pcm_to_wav  # noqa: E402
from web_voice.server import _full_turn_response  # noqa: E402


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

    def transcribe_turn(self, audio, envelope, telemetry=None, *, received_ms=None, detect_end_of_turn=True):
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


class _FakeStreamingBackend:
    """Backend whose `answer_stream` yields one CHUNK per sentence, then a DONE with the
    full text — mirrors the real guarded SSE stream so the batch pipeline synthesizes a
    separate TTS frame per sentence (the BUG-015 scenario)."""

    name = "fake-stream-backend"

    def __init__(self, sentences: list[str]) -> None:
        self._sentences = sentences

    def answer_stream(self, request, control=None):
        for sentence in self._sentences:
            yield AnswerStreamEvent(kind=CHUNK, text=sentence)
        yield AnswerStreamEvent(
            kind=DONE, text=" ".join(self._sentences), confidence=0.9, grounded=True
        )


class FullTurnResponseTest(unittest.IsolatedAsyncioTestCase):
    """BUG-015: the batch `/turn` must return every synthesized sentence, not just the last."""

    def setUp(self) -> None:
        # Force the streaming lever on for a deterministic multi-sentence path regardless of
        # the ambient environment; restore it in tearDown.
        self._prev = os.environ.get("VOICE_BACKEND_STREAM")
        os.environ["VOICE_BACKEND_STREAM"] = "1"

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("VOICE_BACKEND_STREAM", None)
        else:
            os.environ["VOICE_BACKEND_STREAM"] = self._prev

    async def test_streamed_answer_wraps_every_sentence_not_just_last(self) -> None:
        # GIVEN a backend that streams three sentences through the batch pipeline
        ingress = _FakeIngress(_transcript(SttOutcome.SUCCESS, text="facture"))
        egress = _FakeEgress()
        backend = _FakeStreamingBackend(["Phrase une.", "Phrase deux.", "Phrase trois."])
        # WHEN a batch turn runs
        result = await run_batch_turn(b"\x01", _envelope(), ingress=ingress, egress=egress, backend=backend)
        # THEN the capture sink accumulated every sentence's PCM in order
        self.assertEqual(
            result.audio,
            b"AUDIO:Phrase une." + b"AUDIO:Phrase deux." + b"AUDIO:Phrase trois.",
        )
        # AND tts_response holds only the LAST sentence (the pre-fix truncation source)
        self.assertEqual(result.tts_response.result.audio, b"AUDIO:Phrase trois.")
        # AND the turn response wraps the FULL accumulated audio, so no sentence is dropped
        full = _full_turn_response(result)
        self.assertEqual(full.wav, pcm_to_wav(result.audio, 16000))
        self.assertIn(b"AUDIO:Phrase une.", full.wav)
        self.assertIn(b"AUDIO:Phrase deux.", full.wav)

    def test_full_turn_response_falls_back_to_last_when_sink_is_empty(self) -> None:
        # GIVEN a result with no accumulated sink audio but a last synthesis present
        last = SimpleNamespace(result=SimpleNamespace(audio_format="pcm_16000"), wav=b"WAV:last")
        result = SimpleNamespace(audio=b"", tts_response=last)
        # WHEN the full response is built THEN it falls back to the last synthesis unchanged
        self.assertIs(_full_turn_response(result), last)


if __name__ == "__main__":
    unittest.main()
