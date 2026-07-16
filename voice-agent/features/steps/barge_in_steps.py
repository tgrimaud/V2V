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
from web_voice.end_of_turn import DEFAULT_AMPLITUDE_THRESHOLD, StreamingEndOfTurnDetector
from web_voice.streaming_stt_processor import StreamingSttProcessor
from web_voice.streaming_tts_processor import StreamingTtsProcessor

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = (SAMPLE_RATE * FRAME_MS // 1000) * 2


def _speech_frame() -> InputAudioRawFrame:
    pcm = (5000).to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)
    return InputAudioRawFrame(audio=pcm, sample_rate=SAMPLE_RATE, num_channels=1)


def _silence_frame() -> InputAudioRawFrame:
    return InputAudioRawFrame(audio=b"\x00" * FRAME_BYTES, sample_rate=SAMPLE_RATE, num_channels=1)


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
    """Plays one chunk, then blocks so the answer is 'in flight' when the barge-in hits."""

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


class _PlainTtsSession:
    """Plays one chunk and finishes: a previous answer that already stopped playing."""

    def __init__(self):
        self.closed = False

    async def synthesize(self, text):
        self.text = text

    async def stream(self):
        yield AudioChunk(b"\x01\x02")

    async def aclose(self):
        self.closed = True


class _TtsProvider:
    name = "fake-streaming-tts"

    def __init__(self, session):
        self._session = session

    async def open(self):
        return self._session


class _Source(FrameProcessor):
    """Pushes `head` frames (the bot's answer), waits so the TTS starts playing, then
    pushes `tail` frames (the customer speaking) so onset lands mid-answer."""

    def __init__(self, head, tail):
        super().__init__()
        self._head = head
        self._tail = tail

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            for f in self._head:
                await self.push_frame(f, FrameDirection.DOWNSTREAM)
            await asyncio.sleep(0.3)
            for f in self._tail:
                await self.push_frame(f, FrameDirection.DOWNSTREAM)


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


def _build(context, tts_session):
    context.telemetry = TelemetryRecorder()
    envelope = SimpleNamespace(
        correlation_id="qa-barge-in", channel="web_voice", external_session_id="qa"
    )
    detector = StreamingEndOfTurnDetector(
        sample_rate_hz=SAMPLE_RATE,
        silence_window_ms=100,
        amplitude_threshold=DEFAULT_AMPLITUDE_THRESHOLD,
        min_utterance_ms=20,
    )
    context.stt = StreamingSttProcessor(
        _SttProvider(_SttSession([PartialTranscript("attends")], "attends")),
        envelope,
        context.telemetry,
        detector=detector,
    )
    context.tts_session = tts_session
    context.tts = StreamingTtsProcessor(
        _TtsProvider(context.tts_session), envelope, context.telemetry
    )


async def _run(context, head, tail):
    sink = _Sink()
    pipeline = Pipeline([_Source(head, tail), context.stt, context.tts, sink])
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
        while not sink.finals and loop.time() < deadline:
            await asyncio.sleep(0.02)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink


def _has_barge_in(context):
    return any(e.name == "voice.barge_in.detected" for e in context.telemetry.events())


@given("the bot is speaking an answer on the streaming voice loop")
def step_bot_speaking(context):
    _build(context, _GatedTtsSession())
    context.head = [BotStartedSpeakingFrame(), TextFrame(text="voici votre explication de facture")]
    context.tail = [_speech_frame()] * 3 + [_silence_frame()] * 10


@given("the bot is idle on the streaming voice loop")
def step_bot_idle(context):
    _build(context, _PlainTtsSession())
    # No BotStartedSpeakingFrame: the bot is not speaking. The previous answer already
    # finished playing (plain session completes), then the customer speaks a normal turn.
    context.head = [TextFrame(text="reponse precedente")]
    context.tail = [_speech_frame()] * 3 + [_silence_frame()] * 10


@when("the customer starts speaking while the bot is speaking")
def step_customer_barges_in(context):
    context.sink = asyncio.run(_run(context, context.head, context.tail))


@when("the customer speaks a normal turn")
def step_customer_normal_turn(context):
    context.sink = asyncio.run(_run(context, context.head, context.tail))


@then("the spoken answer is interrupted")
def step_answer_interrupted(context):
    events = [e.name for e in context.telemetry.events()]
    assert "tts.interrupted" in events, events
    # Only the single already-played chunk was emitted before the cut.
    assert context.sink.audio == [b"\x01\x02"], context.sink.audio
    assert context.tts_session.closed


@then("an interruption is broadcast to the voice pipeline")
def step_interruption_broadcast(context):
    assert context.sink.interruptions >= 1, context.sink.interruptions


@then("the barge-in is observable via OpenTelemetry")
def step_barge_in_observable(context):
    assert _has_barge_in(context)
    metric_names = {m.name for m in context.telemetry.metrics()}
    assert "voice.barge_in.count" in metric_names, metric_names


@then("the customer's new utterance is transcribed as the next turn")
def step_new_utterance_transcribed(context):
    assert context.sink.finals == ["attends"], context.sink.finals


@then("no interruption is broadcast to the voice pipeline")
def step_no_interruption(context):
    assert context.sink.interruptions == 0, context.sink.interruptions


@then("no barge-in is recorded")
def step_no_barge_in(context):
    assert not _has_barge_in(context)


@then("the customer's utterance is transcribed")
def step_utterance_transcribed(context):
    assert context.sink.finals == ["attends"], context.sink.finals
