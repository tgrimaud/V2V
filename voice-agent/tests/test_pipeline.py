"""Tests for the echo processor and the in-memory batch pipeline (TASK-WEB-005, ST-4)."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from pipecat.frames.frames import TextFrame, TranscriptionFrame  # noqa: E402
from pipecat.tests.utils import run_test  # noqa: E402

from stt_validation.models import SttOutcome, TranscriptResult  # noqa: E402
from tts_synthesis.models import SynthesisResult, TtsOutcome  # noqa: E402
from voice_pipeline.echo import EchoProcessor  # noqa: E402
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


class _FakeIngress:
    def __init__(self, result: TranscriptResult) -> None:
        self._result = result
        self.calls: list[tuple] = []

    def transcribe_turn(self, audio, envelope, telemetry=None, *, received_ms=None):
        self.calls.append((audio, envelope, telemetry, received_ms))
        return self._result


class _FakeEgress:
    """Echoes the text into fake PCM so parity is deterministic."""

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


class EchoProcessorTest(unittest.IsolatedAsyncioTestCase):
    async def test_converts_transcription_frame_into_plain_text_frame(self) -> None:
        # GIVEN an echo processor and an upstream transcription
        processor = EchoProcessor()
        # WHEN a TranscriptionFrame flows through
        down, _up = await run_test(
            processor,
            frames_to_send=[TranscriptionFrame(text="bonjour", user_id="u", timestamp="")],
        )
        # THEN a plain TextFrame with the same text is emitted (no transcription frame)
        self.assertEqual([f for f in down if isinstance(f, TranscriptionFrame)], [])
        plain = [f for f in down if isinstance(f, TextFrame) and not isinstance(f, TranscriptionFrame)]
        self.assertEqual(len(plain), 1)
        self.assertEqual(plain[0].text, "bonjour")


class RunBatchTurnTest(unittest.IsolatedAsyncioTestCase):
    async def test_success_collects_synthesized_audio_end_to_end(self) -> None:
        # GIVEN an ingress that transcribes and an egress that echoes to PCM
        ingress = _FakeIngress(_transcript(SttOutcome.SUCCESS, text="hello"))
        egress = _FakeEgress()
        envelope = SimpleNamespace(external_session_id="s", correlation_id="c")
        # WHEN a turn runs through the pipeline
        result = await run_batch_turn(b"\x01\x02", envelope, ingress=ingress, egress=egress)
        # THEN the transcript is echoed, synthesized and collected as audio
        self.assertEqual(result.transcript_result.transcript, "hello")
        self.assertEqual(egress.calls[0][0], "hello")  # echo fed the transcript to TTS
        self.assertEqual(result.audio, b"AUDIO:hello")
        self.assertIs(result.tts_response.result.outcome, TtsOutcome.SUCCESS)

    async def test_stt_failure_produces_no_audio_and_skips_tts(self) -> None:
        # GIVEN an ingress that fails
        ingress = _FakeIngress(_transcript(SttOutcome.FAILED))
        egress = _FakeEgress()
        # WHEN a turn runs
        result = await run_batch_turn(b"\x01", SimpleNamespace(), ingress=ingress, egress=egress)
        # THEN no transcript flows, TTS is never called, and no audio is produced
        self.assertIs(result.transcript_result.outcome, SttOutcome.FAILED)
        self.assertEqual(egress.calls, [])
        self.assertIsNone(result.tts_response)
        self.assertEqual(result.audio, b"")

    async def test_passes_audio_and_received_ms_to_ingress(self) -> None:
        # GIVEN an ingress and a known audio buffer + received window
        ingress = _FakeIngress(_transcript(SttOutcome.SUCCESS, text="x"))
        egress = _FakeEgress()
        # WHEN a turn runs with a received window
        await run_batch_turn(b"\xaa\xbb", SimpleNamespace(), ingress=ingress, egress=egress, received_ms=7.0)
        # THEN the ingress got the exact audio and window
        audio, _env, _tel, received_ms = ingress.calls[0]
        self.assertEqual(audio, b"\xaa\xbb")
        self.assertEqual(received_ms, 7.0)


if __name__ == "__main__":
    unittest.main()
