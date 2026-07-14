"""Tests for the Pipecat STT frame processor (TASK-WEB-005, ST-2)."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from pipecat.frames.frames import InputAudioRawFrame, TranscriptionFrame  # noqa: E402
from pipecat.tests.utils import run_test  # noqa: E402

from stt_validation.models import SttOutcome, TranscriptResult  # noqa: E402
from voice_pipeline.stt_service import SttFrameProcessor  # noqa: E402


def _result(outcome: SttOutcome, transcript: str = "") -> TranscriptResult:
    return TranscriptResult(
        transcript=transcript,
        provider="fake-stt",
        outcome=outcome,
        duration_ms=1.0,
        stt_request_ms=1.0,
        correlation_id="corr-1",
        error_code=None if outcome is SttOutcome.SUCCESS else "boom",
        error_reason=None if outcome is SttOutcome.SUCCESS else "sanitized",
    )


class _FakeIngress:
    def __init__(self, result: TranscriptResult) -> None:
        self._result = result
        self.calls: list[tuple] = []

    def transcribe_turn(self, audio, envelope, telemetry=None, *, received_ms=None):
        self.calls.append((audio, envelope, telemetry, received_ms))
        return self._result


def _audio_frame(audio: bytes = b"\x01\x02\x03\x04") -> InputAudioRawFrame:
    return InputAudioRawFrame(audio=audio, sample_rate=16000, num_channels=1)


class SttFrameProcessorTest(unittest.IsolatedAsyncioTestCase):
    async def test_success_emits_a_transcription_frame(self) -> None:
        # GIVEN an ingress that transcribes successfully
        ingress = _FakeIngress(_result(SttOutcome.SUCCESS, transcript="bonjour"))
        envelope = SimpleNamespace(external_session_id="sess-1")
        processor = SttFrameProcessor(ingress, envelope)
        # WHEN a whole-utterance audio frame flows through
        down, _up = await run_test(processor, frames_to_send=[_audio_frame()])
        # THEN a TranscriptionFrame carrying the transcript is emitted downstream
        transcripts = [f for f in down if isinstance(f, TranscriptionFrame)]
        self.assertEqual(len(transcripts), 1)
        self.assertEqual(transcripts[0].text, "bonjour")
        self.assertEqual(transcripts[0].user_id, "sess-1")
        self.assertIs(processor.result.outcome, SttOutcome.SUCCESS)

    async def test_failure_emits_no_transcription_frame(self) -> None:
        # GIVEN an ingress that fails
        ingress = _FakeIngress(_result(SttOutcome.FAILED))
        processor = SttFrameProcessor(ingress, SimpleNamespace(external_session_id="s"))
        # WHEN an audio frame flows through
        down, _up = await run_test(processor, frames_to_send=[_audio_frame()])
        # THEN no transcript is invented downstream, and the outcome is surfaced
        self.assertEqual([f for f in down if isinstance(f, TranscriptionFrame)], [])
        self.assertIs(processor.result.outcome, SttOutcome.FAILED)

    async def test_unavailable_emits_no_transcription_frame(self) -> None:
        # GIVEN an ingress that reports no usable speech
        ingress = _FakeIngress(_result(SttOutcome.UNAVAILABLE))
        processor = SttFrameProcessor(ingress, SimpleNamespace(external_session_id="s"))
        # WHEN an audio frame flows through
        down, _up = await run_test(processor, frames_to_send=[_audio_frame()])
        # THEN nothing is spoken and the outcome is UNAVAILABLE
        self.assertEqual([f for f in down if isinstance(f, TranscriptionFrame)], [])
        self.assertIs(processor.result.outcome, SttOutcome.UNAVAILABLE)

    async def test_delegates_raw_audio_envelope_and_received_ms_to_ingress(self) -> None:
        # GIVEN an ingress and a known audio buffer + received window
        ingress = _FakeIngress(_result(SttOutcome.SUCCESS, transcript="x"))
        envelope = SimpleNamespace(external_session_id="sess-9")
        telemetry = object()
        processor = SttFrameProcessor(ingress, envelope, telemetry, received_ms=12.5)
        # WHEN an audio frame flows through
        await run_test(processor, frames_to_send=[_audio_frame(b"\xaa\xbb")])
        # THEN the ingress received the exact audio, envelope, telemetry and window
        self.assertEqual(len(ingress.calls), 1)
        audio, env, tel, received_ms = ingress.calls[0]
        self.assertEqual(audio, b"\xaa\xbb")
        self.assertIs(env, envelope)
        self.assertIs(tel, telemetry)
        self.assertEqual(received_ms, 12.5)


if __name__ == "__main__":
    unittest.main()
