import asyncio
import warnings
from types import SimpleNamespace

from behave import given, then, when
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from stt_validation.streaming import FinalTranscript, PartialTranscript
from tts_synthesis.streaming import AudioChunk
from voice_common.telemetry import TelemetryRecorder
from web_voice.control_signal_processor import CONTROL_SIGNAL_EVENT, ControlSignalProcessor
from web_voice.control_signals import ControlSignal, ControlSignalSource, ControlSignalType
from web_voice.end_of_turn import DEFAULT_AMPLITUDE_THRESHOLD, StreamingEndOfTurnDetector
from web_voice.streaming_stt_processor import StreamingSttProcessor
from web_voice.streaming_tts_processor import StreamingTtsProcessor

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = (SAMPLE_RATE * FRAME_MS // 1000) * 2


def _speech_frame() -> InputAudioRawFrame:
    pcm = (5000).to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)
    return InputAudioRawFrame(audio=pcm, sample_rate=SAMPLE_RATE, num_channels=1)


class _DelayedSource(ControlSignalSource):
    """Emits one control signal after a short delay so the pipeline is mid-turn."""

    def __init__(self, signal_type, *, delay_s=0.25):
        self._signal_type = signal_type
        self._delay_s = delay_s
        self.closed = False

    async def signals(self):
        await asyncio.sleep(self._delay_s)
        yield ControlSignal(self._signal_type)
        # Stay alive until the consumer task is cancelled on teardown.
        await asyncio.Event().wait()

    async def close(self) -> None:
        self.closed = True


class _SttSession:
    def __init__(self, partials, final_text):
        self._queued = list(partials)
        self._released = []
        self._final_text = final_text
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
        return FinalTranscript(self._final_text)

    async def aclose(self):
        self.closed = True


class _SttProvider:
    name = "fake-streaming-stt"

    def __init__(self, session):
        self._session = session

    async def open(self):
        return self._session


class _GatedTtsSession:
    def __init__(self):
        self._gate = asyncio.Event()
        self.closed = False

    async def synthesize(self, text):
        self.text = text

    async def stream(self):
        yield AudioChunk(b"\x01\x02")
        await self._gate.wait()

    async def aclose(self):
        self.closed = True


class _TtsProvider:
    name = "fake-streaming-tts"

    def __init__(self, session):
        self._session = session

    async def open(self):
        return self._session


class _AudioSource(FrameProcessor):
    def __init__(self, frames):
        super().__init__()
        self._frames = frames

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            for extra in self._frames:
                await self.push_frame(extra, FrameDirection.DOWNSTREAM)


class _Sink(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.audio = []
        self.finals = []
        self.interruptions = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            self.audio.append(frame.audio)
        elif isinstance(frame, TranscriptionFrame):
            self.finals.append(frame.text)
        elif isinstance(frame, InterruptionFrame):
            self.interruptions += 1
        await self.push_frame(frame, direction)


def _envelope():
    return SimpleNamespace(
        correlation_id="qa-ws-029", conversation_id="conv-029", channel="web_voice",
        external_session_id="qa",
    )


def _build_stt(context, final_text):
    detector = StreamingEndOfTurnDetector(
        sample_rate_hz=SAMPLE_RATE,
        # Large window: the energy detector will NOT finalize on its own within the test,
        # so a finalized turn can only have come from the control source.
        silence_window_ms=100000,
        amplitude_threshold=DEFAULT_AMPLITUDE_THRESHOLD,
        min_utterance_ms=20,
    )
    return StreamingSttProcessor(
        _SttProvider(_SttSession([PartialTranscript(final_text)], final_text)),
        _envelope(),
        context.telemetry,
        detector=detector,
    )


async def _run(context, head_frames, predicate):
    sink = _Sink()
    control = ControlSignalProcessor(
        telemetry=context.telemetry, correlation_id="qa-ws-029", source=context.source
    )
    stages = [_AudioSource(head_frames), control, context.stt]
    if getattr(context, "tts", None) is not None:
        stages.append(context.tts)
    stages.append(sink)
    pipeline = Pipeline(stages)
    loop = asyncio.get_event_loop()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask

        task = PipelineTask(
            pipeline, params=PipelineParams(), enable_rtvi=False,
            enable_turn_tracking=False, cancel_on_idle_timeout=False, check_dangling_tasks=False,
        )
        run = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        deadline = loop.time() + 2.5
        while not predicate(sink) and loop.time() < deadline:
            await asyncio.sleep(0.02)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink


def _control_signals(context):
    return [
        e.attributes["signal"]
        for e in context.telemetry.events()
        if e.name == CONTROL_SIGNAL_EVENT
    ]


@given("a streaming voice loop fed by a pluggable control source")
def step_loop_with_source(context):
    context.telemetry = TelemetryRecorder()
    context.stt = _build_stt(context, "bonjour")
    context.tts = None
    context.source = _DelayedSource(ControlSignalType.END_OF_TURN)


@given("the customer is speaking with no trailing silence")
def step_speaking_no_silence(context):
    # Speech only — no trailing-silence frames, so the energy detector keeps buffering.
    context.head = [_speech_frame()] * 3


@when("the control source emits an end-of-turn signal")
def step_source_end_of_turn(context):
    context.sink = asyncio.run(_run(context, context.head, lambda sink: bool(sink.finals)))


@then("the current turn is finalized and transcribed")
def step_turn_finalized(context):
    assert context.sink.finals == ["bonjour"], context.sink.finals


@then("the end-of-turn came from the control source, not the energy detector")
def step_eot_from_control(context):
    assert "end_of_turn" in _control_signals(context), _control_signals(context)
    assert context.source.closed


@given("the bot is speaking an answer on the streaming voice loop with a control source")
def step_bot_speaking_with_source(context):
    context.telemetry = TelemetryRecorder()
    context.stt = _build_stt(context, "attends")
    context.tts_session = _GatedTtsSession()
    context.tts = StreamingTtsProcessor(_TtsProvider(context.tts_session), _envelope(), context.telemetry)
    context.source = _DelayedSource(ControlSignalType.BARGE_IN, delay_s=0.3)
    context.head = [BotStartedSpeakingFrame(), TextFrame(text="voici votre explication de facture")]


@when("the control source emits a barge-in signal")
def step_source_barge_in(context):
    context.sink = asyncio.run(_run(context, context.head, lambda sink: sink.interruptions >= 1))


@then("the spoken answer is cut and an interruption is broadcast")
def step_answer_cut(context):
    events = [e.name for e in context.telemetry.events()]
    assert "tts.interrupted" in events, events
    assert context.sink.interruptions >= 1, context.sink.interruptions
    assert context.tts_session.closed


@then("the barge-in is observable as a Genesys-named control signal")
def step_barge_in_control_signal(context):
    assert "barge_in" in _control_signals(context), _control_signals(context)
