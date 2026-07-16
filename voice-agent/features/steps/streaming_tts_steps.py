import asyncio
import warnings
from types import SimpleNamespace

from behave import given, then, when
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    StartFrame,
    TextFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from tts_synthesis.providers import EmptyTextError
from tts_synthesis.streaming import AudioChunk
from voice_common.telemetry import TelemetryRecorder
from web_voice.streaming_tts_processor import TTS_FIRST_AUDIO_SPAN, StreamingTtsProcessor


class _FakeSession:
    def __init__(self, chunks, *, empty_text=False):
        self._chunks = list(chunks)
        self._empty_text = empty_text
        self.closed = False

    async def synthesize(self, text):
        if self._empty_text:
            raise EmptyTextError("No text to synthesize")

    async def stream(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


class _FakeProvider:
    name = "fake-streaming-tts"

    def __init__(self, session):
        self._session = session
        self.open_count = 0

    async def open(self):
        self.open_count += 1
        return self._session


class _Source(FrameProcessor):
    def __init__(self, frames):
        super().__init__()
        self._frames = frames

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            for f in self._frames:
                await self.push_frame(f, FrameDirection.DOWNSTREAM)


class _Sink(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.audio = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            self.audio.append(frame.audio)
        await self.push_frame(frame, direction)


async def _run(processor, frames):
    sink = _Sink()
    pipeline = Pipeline([_Source(frames), processor, sink])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask

        task = PipelineTask(
            pipeline, params=PipelineParams(), enable_rtvi=False,
            enable_turn_tracking=False, cancel_on_idle_timeout=False, check_dangling_tasks=False,
        )
        run = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        await asyncio.sleep(0.2)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink


def _build(context, session, text):
    context.telemetry = TelemetryRecorder()
    context.provider = _FakeProvider(session)
    envelope = SimpleNamespace(
        correlation_id="qa-stream-tts", channel="web_voice", external_session_id="qa"
    )
    context.processor = StreamingTtsProcessor(context.provider, envelope, context.telemetry)
    context.frames = [TextFrame(text=text)]


@given("a response text ready for the customer with a streaming TTS provider")
def step_response(context):
    session = _FakeSession([AudioChunk(b"\x01\x02"), AudioChunk(b"\x03\x04"), AudioChunk(b"\x05\x06")])
    _build(context, session, "bonjour le monde")


@given("an empty response for the customer with a streaming TTS provider")
def step_empty(context):
    _build(context, _FakeSession([], empty_text=True), "   ")


@when("the answer streams to the streaming TTS processor")
def step_stream(context):
    context.sink = asyncio.run(_run(context.processor, context.frames))


@then("audio chunks are emitted incrementally before synthesis completes")
def step_incremental(context):
    assert context.sink.audio == [b"\x01\x02", b"\x03\x04", b"\x05\x06"], context.sink.audio
    assert context.processor.chunk_count == 3, context.processor.chunk_count


@then("time-to-first-audio is observable via OpenTelemetry")
def step_first_audio_metric(context):
    metric_names = {m.name for m in context.telemetry.metrics()}
    assert "tts.time_to_first_audio_ms" in metric_names, metric_names
    span_names = [s.name for s in context.telemetry.spans()]
    assert TTS_FIRST_AUDIO_SPAN in span_names, span_names


@then("no audio is produced")
def step_no_audio(context):
    assert context.sink.audio == [], context.sink.audio


@then("an unavailable TTS outcome is observable via OpenTelemetry")
def step_unavailable(context):
    assert any(e.name == "tts.unavailable" for e in context.telemetry.events()), [
        e.name for e in context.telemetry.events()
    ]
