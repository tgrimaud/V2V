"""Tests for the Pipecat TTS frame processor (TASK-WEB-005, ST-3)."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from pipecat.frames.frames import TextFrame, TranscriptionFrame, TTSAudioRawFrame  # noqa: E402
from pipecat.tests.utils import run_test  # noqa: E402

from tts_synthesis.models import SynthesisResult, TtsOutcome  # noqa: E402
from voice_pipeline.tts_service import TtsFrameProcessor  # noqa: E402


def _synth(outcome: TtsOutcome, audio: bytes = b"") -> SynthesisResult:
    return SynthesisResult(
        audio=audio,
        provider="fake-tts",
        outcome=outcome,
        duration_ms=1.0,
        tts_request_ms=1.0,
        correlation_id="corr-1",
        audio_format="pcm_16000",
        error_code=None if outcome is TtsOutcome.SUCCESS else "boom",
        error_reason=None if outcome is TtsOutcome.SUCCESS else "sanitized",
    )


def _response(outcome: TtsOutcome, audio: bytes = b"", wav: bytes | None = None):
    return SimpleNamespace(result=_synth(outcome, audio), wav=wav)


class _FakeEgress:
    def __init__(self, response) -> None:
        self._response = response
        self.calls: list[tuple] = []

    def synthesize_turn(self, text, envelope, telemetry=None):
        self.calls.append((text, envelope, telemetry))
        return self._response


class TtsFrameProcessorTest(unittest.IsolatedAsyncioTestCase):
    async def test_success_emits_a_tts_audio_frame(self) -> None:
        # GIVEN an egress that synthesizes audio successfully
        egress = _FakeEgress(_response(TtsOutcome.SUCCESS, audio=b"pcmpcm", wav=b"RIFF...."))
        processor = TtsFrameProcessor(egress, SimpleNamespace())
        # WHEN a plain text frame flows through
        down, _up = await run_test(processor, frames_to_send=[TextFrame(text="bonjour")])
        # THEN a TTSAudioRawFrame carrying the PCM audio is emitted downstream
        audio_frames = [f for f in down if isinstance(f, TTSAudioRawFrame)]
        self.assertEqual(len(audio_frames), 1)
        self.assertEqual(audio_frames[0].audio, b"pcmpcm")
        self.assertEqual(audio_frames[0].sample_rate, 16000)
        self.assertIs(processor.response.result.outcome, TtsOutcome.SUCCESS)

    async def test_unavailable_emits_no_audio_frame(self) -> None:
        # GIVEN an egress that reports empty text / nothing to speak
        egress = _FakeEgress(_response(TtsOutcome.UNAVAILABLE))
        processor = TtsFrameProcessor(egress, SimpleNamespace())
        # WHEN a text frame flows through
        down, _up = await run_test(processor, frames_to_send=[TextFrame(text="")])
        # THEN no audio is invented and the outcome is surfaced
        self.assertEqual([f for f in down if isinstance(f, TTSAudioRawFrame)], [])
        self.assertIs(processor.response.result.outcome, TtsOutcome.UNAVAILABLE)

    async def test_failure_emits_no_audio_frame(self) -> None:
        # GIVEN an egress that fails synthesis
        egress = _FakeEgress(_response(TtsOutcome.FAILED))
        processor = TtsFrameProcessor(egress, SimpleNamespace())
        # WHEN a text frame flows through
        down, _up = await run_test(processor, frames_to_send=[TextFrame(text="x")])
        # THEN nothing is spoken and the outcome is FAILED
        self.assertEqual([f for f in down if isinstance(f, TTSAudioRawFrame)], [])
        self.assertIs(processor.response.result.outcome, TtsOutcome.FAILED)

    async def test_transcription_frame_is_forwarded_not_synthesized(self) -> None:
        # GIVEN an egress and an upstream TranscriptionFrame (a TextFrame subclass)
        egress = _FakeEgress(_response(TtsOutcome.SUCCESS, audio=b"x", wav=b"w"))
        processor = TtsFrameProcessor(egress, SimpleNamespace())
        frame = TranscriptionFrame(text="upstream", user_id="u", timestamp="")
        # WHEN it flows through
        down, _up = await run_test(processor, frames_to_send=[frame])
        # THEN it is forwarded untouched and never synthesized
        self.assertEqual(egress.calls, [])
        self.assertTrue(any(isinstance(f, TranscriptionFrame) for f in down))
        self.assertEqual([f for f in down if isinstance(f, TTSAudioRawFrame)], [])

    async def test_delegates_text_envelope_and_telemetry_to_egress(self) -> None:
        # GIVEN an egress and a known envelope + telemetry
        egress = _FakeEgress(_response(TtsOutcome.SUCCESS, audio=b"a", wav=b"w"))
        envelope = SimpleNamespace(correlation_id="c-1")
        telemetry = object()
        processor = TtsFrameProcessor(egress, envelope, telemetry)
        # WHEN a text frame flows through
        await run_test(processor, frames_to_send=[TextFrame(text="hello there")])
        # THEN the egress received the exact text, envelope and telemetry
        self.assertEqual(len(egress.calls), 1)
        text, env, tel = egress.calls[0]
        self.assertEqual(text, "hello there")
        self.assertIs(env, envelope)
        self.assertIs(tel, telemetry)


if __name__ == "__main__":
    unittest.main()
