"""End-to-end end-of-call farewell steps (TASK-WEB-010, ADR-0035).

Composes the real conversation logic — closing-intent detection -> answer suppression
-> TTS speaking the confirmation/closing -> graceful end — as a single pipeline:

    Source -> CallEndFarewellProcessor -> AnswerProcessor(fake backend) -> StreamingTts -> Sink

The STT half is represented by final `TranscriptionFrame`s pushed by the source (its own
contract is covered by the streaming-STT suites); this feature proves the farewell
conversation flow and the end-of-call reason evidence. The teardown callback mirrors the
signaling layer: it records the `voice.call_end` reason under the call correlation id.
"""

import asyncio
import warnings
from types import SimpleNamespace

from behave import given, then, when
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from conversation_backend import AnswerOutcome, AnswerRequest, AnswerResult
from tts_synthesis.streaming import AudioChunk
from voice_common.telemetry import TelemetryRecorder
from web_voice.call_end_farewell import (
    DEFAULT_CLOSING_MESSAGE,
    DEFAULT_CONFIRM_PROMPT,
    CallEndFarewellProcessor,
)
from web_voice.closing_intent import ClosingIntentDetector
from web_voice.streaming_tts_processor import StreamingTtsProcessor

CORRELATION_ID = "qa-call-end"
END_OF_CALL_EVENT = "voice.call_end"


class _FakeBackend:
    name = "fake-backend"

    def __init__(self) -> None:
        self.transcripts: list[str] = []

    def answer(self, request: AnswerRequest) -> AnswerResult:
        self.transcripts.append(request.transcript)
        return AnswerResult(
            text="voici votre explication", provider=self.name,
            outcome=AnswerOutcome.SUCCESS, correlation_id=request.correlation_id,
        )


class _RecordingTtsSession:
    def __init__(self, spoken: list[str]) -> None:
        self._spoken = spoken
        self.closed = False

    async def synthesize(self, text: str) -> None:
        self._spoken.append(text)

    async def stream(self):
        yield AudioChunk(b"\x01\x02")

    async def aclose(self) -> None:
        self.closed = True


class _RecordingTtsProvider:
    name = "fake-streaming-tts"

    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def open(self):
        return _RecordingTtsSession(self.spoken)


class _Source(FrameProcessor):
    def __init__(self, transcripts: list[str]) -> None:
        super().__init__()
        self._transcripts = transcripts

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            for text in self._transcripts:
                await self.push_frame(
                    TranscriptionFrame(text=text, user_id="u", timestamp=""),
                    FrameDirection.DOWNSTREAM,
                )


class _Sink(FrameProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.audio_frames = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            self.audio_frames += 1
        await self.push_frame(frame, direction)


def _envelope() -> SimpleNamespace:
    return SimpleNamespace(
        correlation_id=CORRELATION_ID, conversation_id="qa-conv", channel="web_voice", language="fr"
    )


def _build(context) -> None:
    from voice_pipeline.answer import AnswerProcessor

    context.telemetry = TelemetryRecorder()
    context.backend = _FakeBackend()
    context.tts_provider = _RecordingTtsProvider()
    envelope = _envelope()
    context.farewell = CallEndFarewellProcessor(
        ClosingIntentDetector(), envelope, context.telemetry, confirm_timeout_s=5.0
    )

    async def _end_call(signal: str) -> None:
        # Mirror the signaling teardown: record the end-of-call reason for pilot review.
        context.telemetry.record(
            END_OF_CALL_EVENT, correlation_id=CORRELATION_ID, reason="customer_farewell", signal=signal
        )

    context.farewell.set_end_call(_end_call)
    context.answer = AnswerProcessor(context.backend, envelope, context.telemetry)
    context.tts = StreamingTtsProcessor(
        context.tts_provider, envelope, context.telemetry, prewarm=False
    )


async def _run(context, transcripts: list[str], expected_spoken: int) -> None:
    sink = _Sink()
    pipeline = Pipeline([_Source(transcripts), context.farewell, context.answer, context.tts, sink])
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
        while len(context.tts_provider.spoken) < expected_spoken and loop.time() < deadline:
            await asyncio.sleep(0.02)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    context.sink = sink


@given("the streaming voice loop is active and the customer has their answer")
def step_loop_active(context):
    _build(context)


@when("the customer says a closing formula and then confirms they are done")
def step_closing_then_done(context):
    asyncio.run(_run(context, ["au revoir", "non merci, c'est tout"], expected_spoken=2))


@when("the customer uses a closing word as part of a longer request")
def step_embedded_closing(context):
    asyncio.run(
        _run(context, ["avant de dire au revoir, j'ai une question sur ma facture"], expected_spoken=1)
    )


@then("the bot asks whether they need anything else")
def step_asks_anything_else(context):
    assert DEFAULT_CONFIRM_PROMPT in context.tts_provider.spoken, context.tts_provider.spoken


@then("the bot plays a short spoken closing")
def step_plays_closing(context):
    assert DEFAULT_CLOSING_MESSAGE in context.tts_provider.spoken, context.tts_provider.spoken
    assert context.sink.audio_frames >= 1, context.sink.audio_frames


@then("the closing turn is not sent to the backend as a question")
def step_closing_not_answered(context):
    # Neither the closing nor the "done" confirmation reached the backend as a question.
    assert context.backend.transcripts == [], context.backend.transcripts


@then("the end-of-call reason is recorded as customer_farewell")
def step_reason_recorded(context):
    end = [e for e in context.telemetry.events() if e.name == END_OF_CALL_EVENT]
    assert len(end) == 1, [e.name for e in context.telemetry.events()]
    assert end[0].attributes["reason"] == "customer_farewell", end[0].attributes


@then("the call is not ended")
def step_call_not_ended(context):
    assert context.farewell.last_end_signal is None, context.farewell.last_end_signal
    assert [e for e in context.telemetry.events() if e.name == END_OF_CALL_EVENT] == []


@then("the turn is answered normally by the backend")
def step_answered_normally(context):
    assert context.backend.transcripts == [
        "avant de dire au revoir, j'ai une question sur ma facture"
    ], context.backend.transcripts
    assert DEFAULT_CONFIRM_PROMPT not in context.tts_provider.spoken, context.tts_provider.spoken
