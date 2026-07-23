"""Tests for the streaming STT frame processor (TASK-STT-010).

Drives PCM frames through `[source -> StreamingSttProcessor -> sink]` with a fake
streaming provider (no network) and asserts it:
- opens the provider only once speech starts, streams partials as
  `InterimTranscriptionFrame` and emits one final `TranscriptionFrame` on end-of-turn;
- owns the `voice.end_of_turn` span and emits the `stt.request` span +
  time-to-first-partial / time-to-final metrics;
- never opens a session for a silence-only stream, discards a sub-minimum click, and
  degrades safely (no final frame) on a provider error;
- finalizes on `EndFrame` (client stop) when no full silence window elapsed.
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
    BotStartedSpeakingFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    StartFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402

from stt_validation.streaming import FinalTranscript, PartialTranscript, StreamingSttError  # noqa: E402
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice.end_of_turn import (  # noqa: E402
    DEFAULT_AMPLITUDE_THRESHOLD,
    END_OF_TURN_SPAN,
    StreamingEndOfTurnDetector,
)
from web_voice.streaming_stt_processor import STT_REQUEST_SPAN, StreamingSttProcessor  # noqa: E402

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = (SAMPLE_RATE * FRAME_MS // 1000) * 2


def _detector(min_utterance_ms: float = 20.0) -> StreamingEndOfTurnDetector:
    # Fast windows so tests fire end-of-turn on short synthetic clips.
    return StreamingEndOfTurnDetector(
        sample_rate_hz=SAMPLE_RATE,
        silence_window_ms=100,
        amplitude_threshold=DEFAULT_AMPLITUDE_THRESHOLD,
        min_utterance_ms=min_utterance_ms,
    )


def _processor(provider, telemetry=None, *, min_utterance_ms: float = 20.0) -> StreamingSttProcessor:
    return StreamingSttProcessor(
        provider, _envelope(), telemetry, detector=_detector(min_utterance_ms)
    )


def _speech_frame() -> InputAudioRawFrame:
    pcm = (5000).to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)
    return InputAudioRawFrame(audio=pcm, sample_rate=SAMPLE_RATE, num_channels=1)


def _silence_frame() -> InputAudioRawFrame:
    return InputAudioRawFrame(audio=b"\x00" * FRAME_BYTES, sample_rate=SAMPLE_RATE, num_channels=1)


def _echo_frame() -> InputAudioRawFrame:
    # Above the speech-onset threshold (1000) but below the barge-in threshold (2500):
    # models the bot's own residual echo after browser echo cancellation. Opens the STT
    # session but must NOT be treated as a barge-in (TASK-WEB-008 anti-echo gate).
    pcm = (1500).to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)
    return InputAudioRawFrame(audio=pcm, sample_rate=SAMPLE_RATE, num_channels=1)


class FakeSession:
    """Releases one scripted partial per audio frame; folds all into the final."""

    def __init__(self, partials, final_text, *, error=None):
        self._queued = list(partials)
        self._released: list[PartialTranscript] = []
        self._final_text = final_text
        self._error = error
        self.finished = False
        self.closed = False

    async def send_audio(self, pcm: bytes) -> None:
        if self._queued:
            self._released.append(self._queued.pop(0))

    def poll_partials(self) -> list[PartialTranscript]:
        out, self._released = self._released, []
        return out

    async def finish(self) -> None:
        self.finished = True

    async def wait_final(self) -> FinalTranscript:
        if self._error is not None:
            raise self._error
        return FinalTranscript(self._final_text)

    async def aclose(self) -> None:
        self.closed = True


class FakeProvider:
    name = "fake-streaming-stt"

    def __init__(self, *sessions):
        self._sessions = list(sessions)
        self.open_count = 0

    async def open(self):
        self.open_count += 1
        return self._sessions.pop(0)


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
        self.finals: list[str] = []
        self.interims: list[str] = []
        self.interruptions = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame):
            self.interims.append(frame.text)
        elif isinstance(frame, TranscriptionFrame):
            self.finals.append(frame.text)
        elif isinstance(frame, InterruptionFrame):
            self.interruptions += 1
        await self.push_frame(frame, direction)


async def _drive(processor: StreamingSttProcessor, frames) -> _Sink:
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


def _envelope() -> SimpleNamespace:
    return SimpleNamespace(
        correlation_id="corr-1",
        conversation_id="conv-1",
        channel="web_voice",
        external_session_id="sess-1",
    )


class StreamingSttProcessorTest(unittest.IsolatedAsyncioTestCase):
    async def test_streams_partials_then_final_on_silence_window(self):
        # GIVEN a provider that yields two partials and a final transcript
        session = FakeSession(
            [PartialTranscript("bonjour"), PartialTranscript("le monde")], "bonjour le monde"
        )
        processor = _processor(FakeProvider(session))
        # WHEN speech streams then a trailing-silence window elapses
        frames = [_speech_frame()] * 3 + [_silence_frame()] * 10
        sink = await _drive(processor, frames)
        # THEN partials were pushed as interims and exactly one final transcript emitted
        self.assertEqual(sink.interims, ["bonjour", "le monde"])
        self.assertEqual(sink.finals, ["bonjour le monde"])
        self.assertEqual(processor.final_count, 1)
        self.assertTrue(session.finished)
        self.assertTrue(session.closed)

    async def test_emits_end_of_turn_and_stt_spans(self):
        # GIVEN telemetry wiring
        telemetry = TelemetryRecorder()
        session = FakeSession([PartialTranscript("facture")], "facture")
        processor = _processor(FakeProvider(session), telemetry)
        # WHEN a full turn streams through
        frames = [_speech_frame()] * 3 + [_silence_frame()] * 10
        await _drive(processor, frames)
        # THEN one voice.end_of_turn span and one stt.request span are recorded
        names = [s.name for s in telemetry.spans()]
        self.assertEqual(names.count(END_OF_TURN_SPAN), 1)
        self.assertEqual(names.count(STT_REQUEST_SPAN), 1)
        stt_span = next(s for s in telemetry.spans() if s.name == STT_REQUEST_SPAN)
        self.assertEqual(stt_span.attributes["correlation_id"], "corr-1")
        self.assertEqual(stt_span.attributes["outcome"], "success")
        # AND both streaming latency metrics are emitted
        metrics = {m.name for m in telemetry.metrics()}
        self.assertIn("stt.time_to_final_ms", metrics)
        self.assertIn("stt.time_to_first_partial_ms", metrics)

    async def test_stamps_per_turn_identity_on_turn_spans(self):
        # GIVEN telemetry wiring on a streaming turn (TASK-WEB-017)
        telemetry = TelemetryRecorder()
        session = FakeSession([PartialTranscript("facture")], "facture")
        processor = _processor(FakeProvider(session), telemetry)
        # WHEN a full turn streams through
        frames = [_speech_frame()] * 3 + [_silence_frame()] * 10
        await _drive(processor, frames)
        # THEN the turn's spans carry the stable conversation id AND a per-turn id, so a
        # multi-turn call can be split per turn (correlation_id stays per-conversation)
        eot = next(s for s in telemetry.spans() if s.name == END_OF_TURN_SPAN)
        stt = next(s for s in telemetry.spans() if s.name == STT_REQUEST_SPAN)
        for span in (eot, stt):
            self.assertEqual(span.attributes["correlation_id"], "corr-1")
            self.assertEqual(span.attributes["conversation_id"], "conv-1")
            self.assertEqual(span.attributes["turn_index"], 1)
            self.assertIsNotNone(span.attributes["message_id"])
        # AND both spans share the SAME per-turn message id (one turn, one id)
        self.assertEqual(eot.attributes["message_id"], stt.attributes["message_id"])

    async def test_begin_turn_advances_index_and_mints_new_message_id(self):
        # GIVEN a processor wired to a recorder (TASK-WEB-017)
        telemetry = TelemetryRecorder()
        processor = _processor(FakeProvider(FakeSession([], "")), telemetry)
        # WHEN two turns begin
        processor._begin_turn()
        telemetry.span("marker", 1.0)
        first = next(s for s in telemetry.spans() if s.name == "marker")
        processor._begin_turn()
        telemetry.span("marker", 2.0)
        second = [s for s in telemetry.spans() if s.name == "marker"][-1]
        # THEN the turn index increments and a fresh message id is minted, while the
        # per-conversation identity stays stable
        self.assertEqual(first.attributes["turn_index"], 1)
        self.assertEqual(second.attributes["turn_index"], 2)
        self.assertNotEqual(first.attributes["message_id"], second.attributes["message_id"])
        self.assertEqual(first.attributes["conversation_id"], "conv-1")
        self.assertEqual(second.attributes["conversation_id"], "conv-1")

    async def test_silence_only_never_opens_a_session(self):
        # GIVEN a stream that carries only silence
        provider = FakeProvider(FakeSession([], ""))
        processor = _processor(provider)
        # WHEN driven through the pipeline
        sink = await _drive(processor, [_silence_frame()] * 12)
        # THEN no session is opened, no final transcript, no interims
        self.assertEqual(provider.open_count, 0)
        self.assertEqual(sink.finals, [])
        self.assertEqual(sink.interims, [])

    async def test_sub_minimum_click_is_discarded(self):
        # GIVEN a single short click (below min_utterance) then silence
        session = FakeSession([PartialTranscript("x")], "x")
        provider = FakeProvider(session)
        processor = _processor(provider, min_utterance_ms=200)
        # WHEN driven through the pipeline
        sink = await _drive(processor, [_speech_frame()] + [_silence_frame()] * 10)
        # THEN a session opened (speech seen) but the click is discarded, no final
        self.assertEqual(provider.open_count, 1)
        self.assertEqual(sink.finals, [])
        self.assertTrue(session.closed)

    async def test_provider_error_degrades_without_final(self):
        # GIVEN the provider fails to produce a final
        session = FakeSession([], "", error=StreamingSttError("boom"))
        telemetry = TelemetryRecorder()
        processor = _processor(FakeProvider(session), telemetry)
        # WHEN a full turn streams through
        frames = [_speech_frame()] * 3 + [_silence_frame()] * 10
        sink = await _drive(processor, frames)
        # THEN no final transcript is pushed and a sanitized stt.failure is recorded
        self.assertEqual(sink.finals, [])
        self.assertTrue(session.closed)
        self.assertTrue(any(e.name == "stt.failure" for e in telemetry.events()))

    async def test_finalizes_on_end_frame_client_stop(self):
        # GIVEN speech with no trailing silence window before the stream ends
        session = FakeSession([PartialTranscript("bonjour")], "bonjour")
        processor = _processor(FakeProvider(session))
        # WHEN only speech frames arrive, then EndFrame (client stop)
        sink = await _drive(processor, [_speech_frame()] * 15)
        # THEN the pending turn is finalized on EndFrame
        self.assertEqual(sink.finals, ["bonjour"])
        self.assertEqual(processor.final_count, 1)

    async def test_barge_in_broadcasts_interruption_when_bot_speaking(self):
        # GIVEN the bot is speaking, then the customer speaks loudly and sustained
        telemetry = TelemetryRecorder()
        session = FakeSession([PartialTranscript("stop")], "stop")
        processor = _processor(FakeProvider(session), telemetry)
        # 6 loud frames (> barge-in threshold) clear the 4-frame confirmation gate
        frames = [BotStartedSpeakingFrame()] + [_speech_frame()] * 6 + [_silence_frame()] * 10
        # WHEN driven through the pipeline
        sink = await _drive(processor, frames)
        # THEN an InterruptionFrame is broadcast downstream and a barge-in is recorded
        self.assertGreaterEqual(sink.interruptions, 1)
        self.assertTrue(any(e.name == "voice.barge_in.detected" for e in telemetry.events()))
        self.assertTrue(any(m.name == "voice.barge_in.count" for m in telemetry.metrics()))
        # AND the barge-in utterance is still captured as the new turn
        self.assertEqual(sink.finals, ["stop"])

    async def test_residual_echo_below_threshold_does_not_barge_in(self):
        # GIVEN the bot is speaking and only its own residual echo re-enters the mic
        # (above the onset threshold, below the barge-in threshold) — the without-
        # headphones case that used to self-interrupt (TASK-WEB-008 anti-echo gate)
        telemetry = TelemetryRecorder()
        session = FakeSession([PartialTranscript("echo")], "echo")
        processor = _processor(FakeProvider(session), telemetry)
        frames = [BotStartedSpeakingFrame()] + [_echo_frame()] * 8 + [_silence_frame()] * 10
        # WHEN driven through the pipeline
        sink = await _drive(processor, frames)
        # THEN no interruption is broadcast and no barge-in is recorded
        self.assertEqual(sink.interruptions, 0)
        self.assertFalse(any(e.name == "voice.barge_in.detected" for e in telemetry.events()))

    async def test_brief_loud_spike_shorter_than_confirmation_does_not_barge_in(self):
        # GIVEN the bot is speaking and a brief loud spike (fewer frames than the
        # confirmation window) hits the mic, then it goes quiet again
        telemetry = TelemetryRecorder()
        session = FakeSession([PartialTranscript("blip")], "blip")
        processor = _processor(FakeProvider(session), telemetry)
        # 2 loud frames (< 4-frame gate), broken by echo-level frames that reset the count
        frames = (
            [BotStartedSpeakingFrame()]
            + [_speech_frame()] * 2 + [_echo_frame()] * 2 + [_speech_frame()] * 2
            + [_silence_frame()] * 10
        )
        # WHEN driven through the pipeline
        sink = await _drive(processor, frames)
        # THEN the spike never reaches the sustained-onset gate: no barge-in
        self.assertEqual(sink.interruptions, 0)
        self.assertFalse(any(e.name == "voice.barge_in.detected" for e in telemetry.events()))

    async def test_no_barge_in_when_bot_not_speaking(self):
        # GIVEN the bot is NOT speaking when the customer speaks (a normal turn)
        telemetry = TelemetryRecorder()
        session = FakeSession([PartialTranscript("bonjour")], "bonjour")
        processor = _processor(FakeProvider(session), telemetry)
        frames = [_speech_frame()] * 3 + [_silence_frame()] * 10
        # WHEN driven through the pipeline
        sink = await _drive(processor, frames)
        # THEN no interruption is broadcast and no barge-in is recorded
        self.assertEqual(sink.interruptions, 0)
        self.assertFalse(any(e.name == "voice.barge_in.detected" for e in telemetry.events()))
        self.assertEqual(sink.finals, ["bonjour"])


if __name__ == "__main__":
    unittest.main()
