"""Tests for the WebRTC channel-egress probe (TASK-WEB-014).

Drives `[source -> ChannelEgressProbe -> sink]` and asserts it:
- emits one `web.voice.egress` span for the FIRST audio frame of a spoken turn, tagged
  as runtime egress on the WebRTC transport, and forwards every frame untouched;
- measures exactly one egress sample per turn (later frames of the same turn are pure
  pass-through), re-arming after a `BotStoppedSpeakingFrame` so multi-turn calls yield
  one egress sample per turn;
- is a pure pass-through (no span, no crash) when telemetry/envelope are absent;
- so the CHANNEL_EGRESS slice is measured on the streaming path and the mouth-to-ear
  composite can fold it in.
"""

import asyncio
import sys
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from pipecat.frames.frames import (  # noqa: E402
    BotStoppedSpeakingFrame,
    EndFrame,
    Frame,
    StartFrame,
    TextFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402

from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice.channel_egress_probe import CHANNEL_EGRESS_SPAN, ChannelEgressProbe  # noqa: E402

SAMPLE_RATE = 16000


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
        self.audio: list[bytes] = []
        self.texts: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            self.audio.append(frame.audio)
        elif isinstance(frame, TextFrame):
            self.texts.append(frame.text)
        await self.push_frame(frame, direction)


def _audio(pcm: bytes) -> TTSAudioRawFrame:
    return TTSAudioRawFrame(audio=pcm, sample_rate=SAMPLE_RATE, num_channels=1)


async def _drive(probe: ChannelEgressProbe, frames, *, expected_audio: int = 1) -> _Sink:
    sink = _Sink()
    pipeline = Pipeline([_Source(frames), probe, sink])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask

        task = PipelineTask(
            pipeline, params=PipelineParams(), enable_rtvi=False,
            enable_turn_tracking=False, cancel_on_idle_timeout=False, check_dangling_tasks=False,
        )
        run = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        deadline = asyncio.get_event_loop().time() + 1.5
        while len(sink.audio) < expected_audio and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.05)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink


def _envelope() -> SimpleNamespace:
    return SimpleNamespace(correlation_id="corr-1", channel="web_voice", external_session_id="sess-1")


def _egress_spans(telemetry: TelemetryRecorder):
    return [s for s in telemetry.spans() if s.name == CHANNEL_EGRESS_SPAN]


class ChannelEgressProbeTest(unittest.IsolatedAsyncioTestCase):
    async def test_emits_one_runtime_egress_span_for_first_audio_frame(self) -> None:
        # GIVEN a probe with telemetry on the WebRTC path
        telemetry = TelemetryRecorder()
        probe = ChannelEgressProbe(_envelope(), telemetry, provider_name="gradium-tts-streaming")

        # WHEN a single audio frame flows through
        sink = await _drive(probe, [_audio(b"\x01\x02\x03\x04")])

        # THEN the frame is forwarded AND one egress span is emitted, tagged as runtime egress
        self.assertEqual(sink.audio, [b"\x01\x02\x03\x04"])
        spans = _egress_spans(telemetry)
        self.assertEqual(len(spans), 1)
        self.assertEqual(probe.egress_count, 1)
        attrs = spans[0].attributes
        self.assertEqual(attrs["correlation_id"], "corr-1")
        self.assertEqual(attrs["transport"], "webrtc")
        self.assertEqual(attrs["measure"], "runtime_egress")
        self.assertEqual(attrs["provider"], "gradium-tts-streaming")
        self.assertEqual(attrs["audio_bytes"], 4)
        # AND a matching structured event is recorded
        self.assertTrue(any(e.name == "web.voice.egress.sent" for e in telemetry.events()))

    async def test_measures_only_the_first_frame_of_a_turn(self) -> None:
        # GIVEN three audio frames of a single spoken turn
        telemetry = TelemetryRecorder()
        probe = ChannelEgressProbe(_envelope(), telemetry)

        # WHEN they flow through
        sink = await _drive(probe, [_audio(b"aa"), _audio(b"bb"), _audio(b"cc")], expected_audio=3)

        # THEN every frame is forwarded but only the first is measured (one egress sample)
        self.assertEqual(sink.audio, [b"aa", b"bb", b"cc"])
        self.assertEqual(probe.egress_count, 1)
        self.assertEqual(len(_egress_spans(telemetry)), 1)

    async def test_rearms_after_bot_stopped_speaking_for_next_turn(self) -> None:
        # GIVEN two spoken turns separated by a BotStoppedSpeakingFrame. Driven directly
        # (not through the runner): BotStoppedSpeakingFrame is a SystemFrame that jumps
        # the queue, so a synthetic pipeline would reorder it ahead of the queued audio.
        # In production it is emitted upstream by the output transport *after* a turn's
        # audio, so this ordered drive matches the real re-arm boundary.
        telemetry = TelemetryRecorder()
        probe = ChannelEgressProbe(_envelope(), telemetry)
        pushed: list[Frame] = []

        async def _collect(frame: Frame, direction: FrameDirection) -> None:
            pushed.append(frame)

        probe.push_frame = _collect  # type: ignore[method-assign]

        # WHEN turn 1 audio, an end-of-speech marker (upstream), then turn 2 audio flow through
        await probe.process_frame(_audio(b"a1"), FrameDirection.DOWNSTREAM)
        await probe.process_frame(BotStoppedSpeakingFrame(), FrameDirection.UPSTREAM)
        await probe.process_frame(_audio(b"a2"), FrameDirection.DOWNSTREAM)

        # THEN each turn contributes exactly one egress sample, and all frames are forwarded
        self.assertEqual(probe.egress_count, 2)
        self.assertEqual(len(_egress_spans(telemetry)), 2)
        self.assertEqual([type(f).__name__ for f in pushed],
                         ["TTSAudioRawFrame", "BotStoppedSpeakingFrame", "TTSAudioRawFrame"])

    async def test_non_audio_frames_pass_through_without_a_span(self) -> None:
        # GIVEN a probe and a plain TextFrame (no audio)
        telemetry = TelemetryRecorder()
        probe = ChannelEgressProbe(_envelope(), telemetry)

        # WHEN a text frame then an audio frame flow through
        sink = await _drive(probe, [TextFrame(text="hello"), _audio(b"zz")])

        # THEN the text is forwarded untouched and only the audio frame produced a span
        self.assertEqual(sink.texts, ["hello"])
        self.assertEqual(sink.audio, [b"zz"])
        self.assertEqual(len(_egress_spans(telemetry)), 1)

    async def test_pure_passthrough_without_telemetry(self) -> None:
        # GIVEN a probe with no telemetry recorder (never invents a span)
        probe = ChannelEgressProbe(_envelope(), telemetry=None)

        # WHEN an audio frame flows through
        sink = await _drive(probe, [_audio(b"pcm")])

        # THEN the audio is still forwarded and no span/crash occurs
        self.assertEqual(sink.audio, [b"pcm"])
        self.assertEqual(probe.egress_count, 1)


if __name__ == "__main__":
    unittest.main()
