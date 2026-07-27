"""Tests for the streaming utterance aggregator (Sprint 6 / TASK-WEB-007).

Drives PCM frames through `[source -> UtteranceAggregator -> sink]` and asserts it
flushes exactly one whole-utterance frame after a trailing-silence window, and never
flushes a sub-`min_utterance_ms` click.
"""

import asyncio
import sys
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from pipecat.frames.frames import EndFrame, Frame, InputAudioRawFrame, StartFrame  # noqa: E402
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402

from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice.end_of_turn import END_OF_TURN_SPAN, SIGNAL_SILENCE_WINDOW  # noqa: E402
from web_voice.utterance_aggregator import UtteranceAggregator  # noqa: E402

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = (SAMPLE_RATE * FRAME_MS // 1000) * 2  # 20 ms PCM16 mono


def _speech_frame() -> InputAudioRawFrame:
    # int16 value 5000 (> amplitude threshold 1000) repeated for one frame.
    pcm = (5000).to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)
    return InputAudioRawFrame(audio=pcm, sample_rate=SAMPLE_RATE, num_channels=1)


def _silence_frame() -> InputAudioRawFrame:
    return InputAudioRawFrame(audio=b"\x00" * FRAME_BYTES, sample_rate=SAMPLE_RATE, num_channels=1)


class _Source(FrameProcessor):
    def __init__(self, frames) -> None:
        super().__init__()
        self._frames = frames

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            for f in self._frames:
                await self.push_frame(f, FrameDirection.DOWNSTREAM)


class _Sink(FrameProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.utterances: list[bytes] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            self.utterances.append(frame.audio)
        await self.push_frame(frame, direction)


async def _drive(aggregator: UtteranceAggregator, frames) -> list[bytes]:
    sink = _Sink()
    pipeline = Pipeline([_Source(frames), aggregator, sink])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask

        task = PipelineTask(
            pipeline, params=PipelineParams(), enable_rtvi=False,
            enable_turn_tracking=False, cancel_on_idle_timeout=False, check_dangling_tasks=False,
        )
        run = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        # Frames are pushed on StartFrame and decided synchronously; a short settle is
        # enough. Exit early once an utterance flushes (positive case).
        deadline = asyncio.get_event_loop().time() + 2
        while not sink.utterances and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink.utterances


class UtteranceAggregatorTest(unittest.IsolatedAsyncioTestCase):
    async def test_flushes_one_utterance_after_trailing_silence(self) -> None:
        # GIVEN speech then a trailing silence window (>= 100 ms = 5 frames)
        agg = UtteranceAggregator(
            sample_rate_hz=SAMPLE_RATE, silence_window_ms=100, min_utterance_ms=20
        )
        frames = [_speech_frame()] * 3 + [_silence_frame()] * 6
        # WHEN driven through the pipeline
        utterances = await _drive(agg, frames)
        # THEN exactly one whole-utterance frame is flushed, carrying the speech + silence
        self.assertEqual(len(utterances), 1)
        self.assertEqual(agg.flush_count, 1)
        self.assertGreaterEqual(len(utterances[0]), FRAME_BYTES * 3)

    async def test_ignores_a_sub_minimum_click(self) -> None:
        # GIVEN a single short click below min_utterance_ms, then silence
        agg = UtteranceAggregator(
            sample_rate_hz=SAMPLE_RATE, silence_window_ms=100, min_utterance_ms=200
        )
        frames = [_speech_frame()] + [_silence_frame()] * 6
        # WHEN driven through the pipeline
        utterances = await _drive(agg, frames)
        # THEN nothing is flushed (a click is not a turn)
        self.assertEqual(utterances, [])
        self.assertEqual(agg.flush_count, 0)

    async def test_records_end_of_turn_span_on_flush(self) -> None:
        # GIVEN an aggregator with telemetry + envelope (streaming path wiring)
        telemetry = TelemetryRecorder()
        envelope = SimpleNamespace(correlation_id="corr-42", channel="web_voice")
        agg = UtteranceAggregator(
            sample_rate_hz=SAMPLE_RATE,
            silence_window_ms=100,
            min_utterance_ms=20,
            telemetry=telemetry,
            envelope=envelope,
            provider_name="gradium-stt",
        )
        frames = [_speech_frame()] * 3 + [_silence_frame()] * 6
        # WHEN a turn streams through and end-of-turn fires
        utterances = await _drive(agg, frames)
        # THEN one whole-utterance frame is flushed
        self.assertEqual(len(utterances), 1)
        # AND exactly one voice.end_of_turn span is recorded with the turn attributes
        eot_spans = [s for s in telemetry.spans() if s.name == END_OF_TURN_SPAN]
        self.assertEqual(len(eot_spans), 1)
        span = eot_spans[0]
        self.assertEqual(span.attributes["correlation_id"], "corr-42")
        self.assertEqual(span.attributes["channel"], "web_voice")
        self.assertEqual(span.attributes["provider"], "gradium-stt")
        self.assertEqual(span.attributes["end_of_turn_signal"], SIGNAL_SILENCE_WINDOW)
        # AND the detected event mirrors the span for pilot review
        self.assertTrue(
            any(e.name == "voice.end_of_turn.detected" for e in telemetry.events())
        )

    async def test_stamps_per_turn_identity_on_end_of_turn_span(self) -> None:
        # GIVEN an aggregator with telemetry + envelope carrying a conversation id
        telemetry = TelemetryRecorder()
        envelope = SimpleNamespace(
            correlation_id="corr-42", conversation_id="conv-42", channel="web_voice"
        )
        agg = UtteranceAggregator(
            sample_rate_hz=SAMPLE_RATE,
            silence_window_ms=100,
            min_utterance_ms=20,
            telemetry=telemetry,
            envelope=envelope,
        )
        frames = [_speech_frame()] * 3 + [_silence_frame()] * 6
        # WHEN a turn streams through and end-of-turn fires (TASK-WEB-017)
        await _drive(agg, frames)
        # THEN the end_of_turn span carries the stable conversation id and a per-turn id
        span = next(s for s in telemetry.spans() if s.name == END_OF_TURN_SPAN)
        self.assertEqual(span.attributes["correlation_id"], "corr-42")
        self.assertEqual(span.attributes["conversation_id"], "conv-42")
        self.assertEqual(span.attributes["turn_index"], 1)
        self.assertIsNotNone(span.attributes["message_id"])

    async def test_no_span_when_stream_has_no_speech(self) -> None:
        # GIVEN telemetry wiring and a stream that carries only silence
        telemetry = TelemetryRecorder()
        envelope = SimpleNamespace(correlation_id="corr-0", channel="web_voice")
        agg = UtteranceAggregator(
            sample_rate_hz=SAMPLE_RATE, silence_window_ms=100, telemetry=telemetry, envelope=envelope
        )
        frames = [_silence_frame()] * 8
        # WHEN driven through the pipeline
        utterances = await _drive(agg, frames)
        # THEN no turn is invented and no end_of_turn span is recorded
        self.assertEqual(utterances, [])
        self.assertEqual([s for s in telemetry.spans() if s.name == END_OF_TURN_SPAN], [])


if __name__ == "__main__":
    unittest.main()
