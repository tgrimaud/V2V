import asyncio
import warnings
from types import SimpleNamespace

from behave import given, then, when
from pipecat.frames.frames import EndFrame, Frame, InputAudioRawFrame, StartFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from voice_common.telemetry import TelemetryRecorder
from web_voice.end_of_turn import END_OF_TURN_SPAN
from web_voice.utterance_aggregator import UtteranceAggregator

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = (SAMPLE_RATE * FRAME_MS // 1000) * 2


def _speech_frame() -> InputAudioRawFrame:
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


async def _run(aggregator, frames) -> list[bytes]:
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
        deadline = asyncio.get_event_loop().time() + 2
        while not sink.utterances and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink.utterances


def _drive(context, frames) -> None:
    context.telemetry = TelemetryRecorder()
    context.envelope = SimpleNamespace(correlation_id="qa-stream-eot", channel="web_voice")
    aggregator = UtteranceAggregator(
        sample_rate_hz=SAMPLE_RATE,
        silence_window_ms=100,
        min_utterance_ms=20,
        telemetry=context.telemetry,
        envelope=context.envelope,
        provider_name="qa-stt",
    )
    context.utterances = asyncio.run(_run(aggregator, frames))


@given("a stream of speech frames followed by a trailing-silence window")
def step_speech_then_silence(context):
    context.frames = [_speech_frame()] * 3 + [_silence_frame()] * 6


@given("a stream that carries only silence")
def step_only_silence(context):
    context.frames = [_silence_frame()] * 8


@when("the frames are streamed to the utterance aggregator")
def step_stream_frames(context):
    _drive(context, context.frames)


@then("an end-of-turn is fired before the full buffer is available")
def step_end_of_turn_fired(context):
    assert len(context.utterances) == 1, context.utterances


@then("a voice.end_of_turn span with the turn correlation id is recorded")
def step_eot_span_recorded(context):
    spans = [s for s in context.telemetry.spans() if s.name == END_OF_TURN_SPAN]
    assert len(spans) == 1, spans
    assert spans[0].attributes["correlation_id"] == "qa-stream-eot"


@then("no end-of-turn is fired")
def step_no_end_of_turn(context):
    assert context.utterances == [], context.utterances


@then("no voice.end_of_turn span is recorded")
def step_no_eot_span(context):
    assert [s for s in context.telemetry.spans() if s.name == END_OF_TURN_SPAN] == []
