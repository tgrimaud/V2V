import asyncio
import warnings
from types import SimpleNamespace

from behave import given, then, when
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from conversation_backend import DEGRADED_FALLBACK_TEXT
from stt_validation.streaming import FinalTranscript, PartialTranscript, StreamingSttError
from voice_common.telemetry import TelemetryRecorder
from web_voice.end_of_turn import DEFAULT_AMPLITUDE_THRESHOLD, StreamingEndOfTurnDetector
from web_voice.streaming_stt_processor import (
    STT_DEGRADED_SPOKEN_EVENT,
    STT_REQUEST_SPAN,
    StreamingSttProcessor,
)

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = (SAMPLE_RATE * FRAME_MS // 1000) * 2


def _speech_frame() -> InputAudioRawFrame:
    pcm = (5000).to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)
    return InputAudioRawFrame(audio=pcm, sample_rate=SAMPLE_RATE, num_channels=1)


def _silence_frame() -> InputAudioRawFrame:
    return InputAudioRawFrame(audio=b"\x00" * FRAME_BYTES, sample_rate=SAMPLE_RATE, num_channels=1)


class _FakeSession:
    def __init__(self, partials, final_text, *, error=None):
        self._queued = list(partials)
        self._released = []
        self._final_text = final_text
        self._error = error
        self.closed = False

    async def send_audio(self, pcm):
        if self._queued:
            self._released.append(self._queued.pop(0))

    def poll_partials(self):
        out, self._released = self._released, []
        return out

    async def finish(self):
        return None

    async def wait_final(self):
        if self._error is not None:
            raise self._error
        return FinalTranscript(self._final_text)

    async def aclose(self):
        self.closed = True


class _FakeProvider:
    name = "fake-streaming-stt"

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
        self.finals = []
        self.interims = []
        self.texts = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame):
            self.interims.append(frame.text)
        elif isinstance(frame, TranscriptionFrame):
            self.finals.append(frame.text)
        elif type(frame) is TextFrame:
            # Plain answer/degraded TextFrame the TTS stage would synthesise (TASK-WEB-018).
            self.texts.append(frame.text)
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
        deadline = asyncio.get_event_loop().time() + 1.5
        while not sink.finals and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink


def _build(context, session):
    context.telemetry = TelemetryRecorder()
    context.provider = _FakeProvider(session)
    envelope = SimpleNamespace(
        correlation_id="qa-stream-stt", channel="web_voice", external_session_id="qa"
    )
    detector = StreamingEndOfTurnDetector(
        sample_rate_hz=SAMPLE_RATE,
        silence_window_ms=100,
        amplitude_threshold=DEFAULT_AMPLITUDE_THRESHOLD,
        min_utterance_ms=20,
    )
    context.processor = StreamingSttProcessor(
        context.provider, envelope, context.telemetry, detector=detector
    )


@given("a customer speaking on the web voice page with a streaming STT provider")
def step_speaking(context):
    session = _FakeSession(
        [PartialTranscript("bonjour"), PartialTranscript("le monde")], "bonjour le monde"
    )
    _build(context, session)
    context.frames = [_speech_frame()] * 3 + [_silence_frame()] * 10


@given("a silent stream on the web voice page with a streaming STT provider")
def step_silent(context):
    _build(context, _FakeSession([], ""))
    context.frames = [_silence_frame()] * 12


@given("a customer speaking but the streaming STT provider fails to finalize")
def step_failing_finalize(context):
    _build(context, _FakeSession([], "", error=StreamingSttError("boom")))
    context.frames = [_speech_frame()] * 3 + [_silence_frame()] * 10


@when("the audio streams to the streaming STT processor")
def step_stream(context):
    context.sink = asyncio.run(_run(context.processor, context.frames))


@then("partial transcripts are emitted before end-of-turn")
def step_partials(context):
    assert context.sink.interims == ["bonjour", "le monde"], context.sink.interims


@then("a final transcript is produced after end-of-turn")
def step_final(context):
    assert context.sink.finals == ["bonjour le monde"], context.sink.finals


@then("time-to-first-partial and time-to-final are observable via OpenTelemetry")
def step_metrics(context):
    metric_names = {m.name for m in context.telemetry.metrics()}
    assert "stt.time_to_first_partial_ms" in metric_names, metric_names
    assert "stt.time_to_final_ms" in metric_names, metric_names
    span_names = [s.name for s in context.telemetry.spans()]
    assert STT_REQUEST_SPAN in span_names, span_names


@then("no final transcript is produced")
def step_no_final(context):
    assert context.sink.finals == [], context.sink.finals


@then("the streaming provider is never opened")
def step_not_opened(context):
    assert context.provider.open_count == 0, context.provider.open_count


@then("the safe degraded fallback is spoken to the customer")
def step_degraded_spoken(context):
    assert context.sink.texts == [DEGRADED_FALLBACK_TEXT], context.sink.texts


@then("the spoken fallback contains no digit or amount")
def step_no_digit(context):
    spoken = context.sink.texts[0] if context.sink.texts else ""
    assert not any(ch.isdigit() for ch in spoken), spoken


@then("a degraded-spoken outcome event is recorded via OpenTelemetry")
def step_degraded_event(context):
    names = [e.name for e in context.telemetry.events()]
    assert STT_DEGRADED_SPOKEN_EVENT in names, names
