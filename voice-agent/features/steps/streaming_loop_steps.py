"""E2E streaming loop steps (TASK-WEB-009 / US-036).

Composes the real streaming processors into one pipeline:
    source -> StreamingSttProcessor -> AnswerProcessor -> StreamingTtsProcessor -> sink
sharing one TelemetryRecorder and one ChannelEnvelope. It proves a streaming turn
flows from streamed partials to the first incremental bot audio frame and that the
ADR-0018 time_to_first_audio composite is derivable from the emitted spans, all
under a single correlation id. STT/TTS providers are fakes; the backend is the
deterministic stub, so the loop stays offline and repeatable.
"""

import asyncio
import warnings

from behave import given, then, when
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from conversation_backend import StubBackendAdapter
from stt_validation.pipeline_timing import (
    PipelineTimingReport,
    STT,
    per_turn_timings,
    time_to_first_audio_report,
)
from stt_validation.streaming import FinalTranscript, PartialTranscript
from tts_synthesis.streaming import AudioChunk
from voice_common.telemetry import TelemetryRecorder
from voice_pipeline.answer import AnswerProcessor
from web_voice.end_of_turn import DEFAULT_AMPLITUDE_THRESHOLD, StreamingEndOfTurnDetector
from web_voice.envelope import ChannelEnvelope
from web_voice.streaming_stt_processor import StreamingSttProcessor
from web_voice.streaming_tts_processor import StreamingTtsProcessor

CORRELATION_ID = "qa-stream-loop"
SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = (SAMPLE_RATE * FRAME_MS // 1000) * 2


def _speech_frame() -> InputAudioRawFrame:
    pcm = (5000).to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)
    return InputAudioRawFrame(audio=pcm, sample_rate=SAMPLE_RATE, num_channels=1)


def _silence_frame() -> InputAudioRawFrame:
    return InputAudioRawFrame(audio=b"\x00" * FRAME_BYTES, sample_rate=SAMPLE_RATE, num_channels=1)


class _FakeSttSession:
    def __init__(self, partials, final_text):
        self._queued = list(partials)
        self._released: list = []
        self._final_text = final_text

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
        return None


class _FakeSttProvider:
    name = "fake-streaming-stt"

    def __init__(self, session):
        self._session = session

    async def open(self):
        return self._session


class _FakeTtsSession:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def synthesize(self, text):
        return None

    async def stream(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        return None


class _FakeTtsProvider:
    name = "fake-streaming-tts"

    def __init__(self, session):
        self._session = session

    async def open(self):
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
        self.interims: list[str] = []
        self.finals: list[str] = []
        self.audio: list[bytes] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame):
            self.interims.append(frame.text)
        elif isinstance(frame, TranscriptionFrame):
            self.finals.append(frame.text)
        elif isinstance(frame, TTSAudioRawFrame):
            self.audio.append(frame.audio)
        await self.push_frame(frame, direction)


async def _run(processors, frames):
    sink = _Sink()
    pipeline = Pipeline([_Source(frames), *processors, sink])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask

        task = PipelineTask(
            pipeline, params=PipelineParams(), enable_rtvi=False,
            enable_turn_tracking=False, cancel_on_idle_timeout=False, check_dangling_tasks=False,
        )
        run = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        deadline = asyncio.get_event_loop().time() + 3.0
        while not sink.audio and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink


@given("a customer speaking a question on the streaming voice loop")
def step_speaking(context):
    context.telemetry = TelemetryRecorder()
    envelope = ChannelEnvelope.for_web_turn(correlation_id=CORRELATION_ID)
    detector = StreamingEndOfTurnDetector(
        sample_rate_hz=SAMPLE_RATE,
        silence_window_ms=100,
        amplitude_threshold=DEFAULT_AMPLITUDE_THRESHOLD,
        min_utterance_ms=20,
    )
    stt = StreamingSttProcessor(
        _FakeSttProvider(
            _FakeSttSession(
                [PartialTranscript("pourquoi"), PartialTranscript("ma facture")],
                "pourquoi ma facture augmente",
            )
        ),
        envelope,
        context.telemetry,
        detector=detector,
    )
    answer = AnswerProcessor(StubBackendAdapter(), envelope, context.telemetry)
    tts = StreamingTtsProcessor(
        _FakeTtsProvider(_FakeTtsSession([AudioChunk(b"\x01\x02"), AudioChunk(b"\x03\x04"), AudioChunk(b"\x05\x06")])),
        envelope,
        context.telemetry,
    )
    context.processors = [stt, answer, tts]
    context.frames = [_speech_frame()] * 3 + [_silence_frame()] * 10


@when("the streaming loop runs the turn end to end")
def step_run(context):
    context.sink = asyncio.run(_run(context.processors, context.frames))


@then("partial transcripts stream before the final transcript")
def step_partials(context):
    assert context.sink.interims == ["pourquoi", "ma facture"], context.sink.interims
    # The final transcript is consumed by the answer step (spoken back), so it never
    # reaches the sink as a frame; its production is observable via the stt.request
    # (finalize) span emitted after end-of-turn.
    span_names = [s.name for s in context.telemetry.spans()]
    assert "stt.request" in span_names, span_names


@then("the bot answer is spoken back as incremental audio")
def step_incremental_audio(context):
    assert context.sink.audio == [b"\x01\x02", b"\x03\x04", b"\x05\x06"], context.sink.audio


@then("the whole turn shares one correlation id")
def step_one_correlation(context):
    correlations = {s.attributes.get("correlation_id") for s in context.telemetry.spans()}
    assert correlations == {CORRELATION_ID}, correlations


@then("time_to_first_audio is derivable from the turn telemetry")
def step_first_audio_derivable(context):
    composite = time_to_first_audio_report(context.telemetry.spans())
    assert composite.measured, "time_to_first_audio should be derivable from the streaming spans"
    assert composite.report is not None and composite.report.count >= 1
    assert composite.report.p50_ms is not None and composite.report.p50_ms > 0


# --- multi-turn per-turn identity (TASK-WEB-017) ----------------------------------

# Slice spans that make up the latency composites; each must carry a per-turn id so a
# multi-turn call is separable per turn (not just STT — backend and TTS spans too).
_SLICE_SPAN_NAMES = {
    "voice.end_of_turn",
    "stt.request",
    "backend.first_token",
    "backend.request",
    "voice.tts.first_audio",
}


class _MultiSttProvider:
    name = "fake-streaming-stt"

    def __init__(self, sessions):
        self._sessions = list(sessions)

    async def open(self):
        return self._sessions.pop(0)


class _MultiTtsProvider:
    name = "fake-streaming-tts"

    def __init__(self, chunk_lists):
        self._chunk_lists = list(chunk_lists)

    async def open(self):
        return _FakeTtsSession(self._chunk_lists.pop(0))


async def _run_until(processors, frames, min_audio_chunks):
    sink = _Sink()
    pipeline = Pipeline([_Source(frames), *processors, sink])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask

        task = PipelineTask(
            pipeline, params=PipelineParams(), enable_rtvi=False,
            enable_turn_tracking=False, cancel_on_idle_timeout=False, check_dangling_tasks=False,
        )
        run = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        deadline = asyncio.get_event_loop().time() + 5.0
        while len(sink.audio) < min_audio_chunks and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink


@given("a customer asking two questions on the same streaming call")
def step_two_questions(context):
    context.telemetry = TelemetryRecorder()
    envelope = ChannelEnvelope.for_web_turn(correlation_id=CORRELATION_ID)
    context.conversation_id = envelope.conversation_id
    detector = StreamingEndOfTurnDetector(
        sample_rate_hz=SAMPLE_RATE,
        silence_window_ms=100,
        amplitude_threshold=DEFAULT_AMPLITUDE_THRESHOLD,
        min_utterance_ms=20,
    )
    stt = StreamingSttProcessor(
        _MultiSttProvider([
            _FakeSttSession([PartialTranscript("pourquoi")], "pourquoi ma facture augmente"),
            _FakeSttSession([PartialTranscript("et")], "et le mois prochain"),
        ]),
        envelope,
        context.telemetry,
        detector=detector,
    )
    answer = AnswerProcessor(StubBackendAdapter(), envelope, context.telemetry)
    # prewarm disabled so the TTS provider opens exactly one session per turn (two turns).
    tts = StreamingTtsProcessor(
        _MultiTtsProvider([[AudioChunk(b"\x01\x02")], [AudioChunk(b"\x03\x04")]]),
        envelope,
        context.telemetry,
        prewarm=False,
    )
    context.processors = [stt, answer, tts]
    turn = [_speech_frame()] * 3 + [_silence_frame()] * 10
    context.frames = turn + turn


@when("the streaming loop runs both turns end to end")
def step_run_two_turns(context):
    context.sink = asyncio.run(_run_until(context.processors, context.frames, min_audio_chunks=2))


@then("the whole call shares one correlation id")
def step_call_one_correlation(context):
    correlations = {s.attributes.get("correlation_id") for s in context.telemetry.spans()}
    assert correlations == {CORRELATION_ID}, correlations


@then("every slice span of the call carries a per-turn id")
def step_every_slice_span_has_turn_id(context):
    slice_spans = [s for s in context.telemetry.spans() if s.name in _SLICE_SPAN_NAMES]
    assert slice_spans, "no slice spans recorded"
    missing = [s.name for s in slice_spans if s.attributes.get("turn_index") is None]
    assert not missing, f"slice spans missing a per-turn id: {missing}"


@then("the two turns carry distinct per-turn ids under one conversation id")
def step_two_distinct_turn_ids(context):
    spans = context.telemetry.spans()
    turn_indexes = {s.attributes.get("turn_index") for s in spans if s.name in _SLICE_SPAN_NAMES}
    assert turn_indexes == {1, 2}, turn_indexes
    message_ids = {s.attributes.get("message_id") for s in spans if s.name in _SLICE_SPAN_NAMES}
    assert len(message_ids) == 2, message_ids
    conversations = {s.attributes.get("conversation_id") for s in spans if s.name in _SLICE_SPAN_NAMES}
    assert conversations == {context.conversation_id}, conversations


@then("the per-turn report separates the two turns without overwriting slices")
def step_per_turn_report_separates(context):
    spans = context.telemetry.spans()
    rows = per_turn_timings(spans)
    assert [r["turn_index"] for r in rows] == [1, 2], rows
    assert rows[0]["message_id"] != rows[1]["message_id"], rows
    # per-slice distribution keeps one sample per turn (no overwrite)
    report = PipelineTimingReport.from_spans(spans)
    stt = next(s for s in report.slices if s.slice == STT)
    assert stt.report is not None and stt.report.count == 2, stt.report
