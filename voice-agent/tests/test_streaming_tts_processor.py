"""Tests for the streaming TTS frame processor (TASK-WEB-004).

Drives `[source -> StreamingTtsProcessor -> sink]` with a fake streaming provider
(no network) and asserts it:
- streams a plain `TextFrame` as several incremental `TTSAudioRawFrame`s (playback on
  the first chunk), in order;
- forwards a `TranscriptionFrame` untouched (never synthesizes STT output);
- owns the `voice.tts.first_audio` span and emits time-to-first-audio /
  time-to-last-audio metrics;
- reports UNAVAILABLE (no invented audio) on empty text, and degrades safely (no
  audio, sanitized `tts.failure`) on a provider error.
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
    Frame,
    InterimTranscriptionFrame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402

from tts_synthesis.providers import EmptyTextError  # noqa: E402
from tts_synthesis.streaming import AudioChunk, StreamingTtsError  # noqa: E402
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice.streaming_tts_processor import TTS_FIRST_AUDIO_SPAN, StreamingTtsProcessor  # noqa: E402

SAMPLE_RATE = 16000


class FakeSession:
    """Streams scripted PCM chunks; raises `error` (if set) instead of streaming."""

    def __init__(self, chunks, *, error=None, empty_text=False):
        self._chunks = list(chunks)
        self._error = error
        self._empty_text = empty_text
        self.closed = False
        self.synthesized_text = None

    async def synthesize(self, text):
        self.synthesized_text = text
        if self._empty_text:
            raise EmptyTextError("No text to synthesize")

    async def stream(self):
        if self._error is not None:
            raise self._error
        for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


class GatedSession:
    """Streams the first chunks, then blocks forever on a gate.

    Lets a test put a synthesis mid-flight (first audio played, more pending) so a
    barge-in `InterruptionFrame` can cancel it deterministically.
    """

    def __init__(self, first_chunks):
        self._first = list(first_chunks)
        self._gate = asyncio.Event()  # never set: stream stalls until cancelled
        self.closed = False
        self.synthesized_text = None

    async def synthesize(self, text):
        self.synthesized_text = text

    async def stream(self):
        for chunk in self._first:
            yield chunk
        await self._gate.wait()

    async def aclose(self):
        self.closed = True


class FakeProvider:
    name = "fake-streaming-tts"

    def __init__(self, *sessions):
        self._sessions = list(sessions)
        self.open_count = 0

    async def open(self):
        self.open_count += 1
        return self._sessions.pop(0)


class FailingOpenProvider:
    """Fails at connect/handshake time (open raises before any session exists)."""

    name = "fake-streaming-tts"

    def __init__(self, error):
        self._error = error
        self.open_count = 0

    async def open(self):
        self.open_count += 1
        raise self._error


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
        self.transcripts: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            self.audio.append(frame.audio)
        elif isinstance(frame, TranscriptionFrame):
            self.transcripts.append(frame.text)
        elif isinstance(frame, TextFrame):
            self.texts.append(frame.text)
        await self.push_frame(frame, direction)


async def _drive(processor: StreamingTtsProcessor, frames) -> _Sink:
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
        while not sink.audio and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.05)
        from pipecat.frames.frames import EndFrame

        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink


def _envelope() -> SimpleNamespace:
    return SimpleNamespace(correlation_id="corr-1", channel="web_voice", external_session_id="sess-1")


def _processor(provider, telemetry=None) -> StreamingTtsProcessor:
    return StreamingTtsProcessor(provider, _envelope(), telemetry)


class StreamingTtsProcessorTest(unittest.IsolatedAsyncioTestCase):
    async def test_streams_text_as_incremental_audio_frames(self):
        # GIVEN a provider that streams three PCM chunks for the answer text
        session = FakeSession([AudioChunk(b"\x01\x02"), AudioChunk(b"\x03\x04"), AudioChunk(b"\x05\x06")])
        provider = FakeProvider(session)
        processor = _processor(provider)
        # WHEN a plain answer TextFrame flows through
        sink = await _drive(processor, [TextFrame(text="bonjour")])
        # THEN each chunk is pushed as a TTSAudioRawFrame, in order
        self.assertEqual(sink.audio, [b"\x01\x02", b"\x03\x04", b"\x05\x06"])
        self.assertEqual(processor.chunk_count, 3)
        self.assertEqual(session.synthesized_text, "bonjour")
        self.assertTrue(session.closed)

    async def test_emits_first_audio_span_and_latency_metrics(self):
        # GIVEN telemetry wiring
        telemetry = TelemetryRecorder()
        session = FakeSession([AudioChunk(b"\x01\x02"), AudioChunk(b"\x03\x04")])
        processor = _processor(FakeProvider(session), telemetry)
        # WHEN a full synthesis streams through
        await _drive(processor, [TextFrame(text="facture")])
        # THEN one voice.tts.first_audio span is recorded with a success outcome
        spans = [s for s in telemetry.spans() if s.name == TTS_FIRST_AUDIO_SPAN]
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes["outcome"], "success")
        self.assertEqual(spans[0].attributes["correlation_id"], "corr-1")
        # AND both streaming latency metrics are emitted
        metrics = {m.name for m in telemetry.metrics()}
        self.assertIn("tts.time_to_first_audio_ms", metrics)
        self.assertIn("tts.time_to_last_audio_ms", metrics)

    async def test_forwards_transcription_frame_untouched(self):
        # GIVEN a TranscriptionFrame (upstream STT output, a TextFrame subclass)
        session = FakeSession([AudioChunk(b"\x09")])
        provider = FakeProvider(session)
        processor = _processor(provider)
        # WHEN it flows through with a plain answer TextFrame after it
        sink = await _drive(
            processor,
            [TranscriptionFrame(text="question", user_id="u", timestamp=""), TextFrame(text="reponse")],
        )
        # THEN the transcript is forwarded untouched and only the answer is synthesized
        self.assertEqual(sink.transcripts, ["question"])
        self.assertEqual(session.synthesized_text, "reponse")
        self.assertEqual(sink.audio, [b"\x09"])

    async def test_interim_transcription_frame_is_not_synthesized(self):
        # GIVEN an interim partial transcript (a TextFrame subclass, live STT output)
        # followed by the plain answer TextFrame
        session = FakeSession([AudioChunk(b"\x07")])
        provider = FakeProvider(session)
        processor = _processor(provider)
        # WHEN both flow through
        sink = await _drive(
            processor,
            [
                InterimTranscriptionFrame(text="ma question", user_id="u", timestamp=""),
                TextFrame(text="la reponse"),
            ],
        )
        # THEN only the answer is synthesized (the partial is never spoken back)
        self.assertEqual(provider.open_count, 1)
        self.assertEqual(session.synthesized_text, "la reponse")
        self.assertEqual(sink.audio, [b"\x07"])

    async def test_empty_text_reports_unavailable_without_audio(self):
        # GIVEN a session that rejects empty text
        telemetry = TelemetryRecorder()
        session = FakeSession([], empty_text=True)
        processor = _processor(FakeProvider(session), telemetry)
        # WHEN an empty answer TextFrame flows through
        sink = await _drive_no_audio(processor, [TextFrame(text="   ")])
        # THEN no audio is invented and an UNAVAILABLE outcome is recorded
        self.assertEqual(sink.audio, [])
        self.assertTrue(session.closed)
        self.assertTrue(any(e.name == "tts.unavailable" for e in telemetry.events()))

    async def test_provider_error_degrades_without_audio(self):
        # GIVEN the provider fails to stream audio
        telemetry = TelemetryRecorder()
        session = FakeSession([], error=StreamingTtsError("boom"))
        processor = _processor(FakeProvider(session), telemetry)
        # WHEN a synthesis is attempted
        sink = await _drive_no_audio(processor, [TextFrame(text="bonjour")])
        # THEN no audio is pushed and a sanitized tts.failure is recorded
        self.assertEqual(sink.audio, [])
        self.assertTrue(session.closed)
        self.assertTrue(any(e.name == "tts.failure" for e in telemetry.events()))

    async def test_connect_failure_degrades_without_audio(self):
        # GIVEN the provider fails at connect/handshake time (open raises)
        telemetry = TelemetryRecorder()
        provider = FailingOpenProvider(StreamingTtsError("auth rejected at handshake"))
        processor = _processor(provider, telemetry)
        # WHEN a synthesis is attempted
        sink = await _drive_no_audio(processor, [TextFrame(text="bonjour")])
        # THEN the connect fault is a sanitized tts.failure, not a silent dead turn
        self.assertEqual(provider.open_count, 1)
        self.assertEqual(sink.audio, [])
        self.assertTrue(any(e.name == "tts.failure" for e in telemetry.events()))

    async def test_zero_chunks_reports_unavailable_without_audio(self):
        # GIVEN the provider streams no audio at all (text present, zero chunks)
        telemetry = TelemetryRecorder()
        session = FakeSession([])
        processor = _processor(FakeProvider(session), telemetry)
        # WHEN a synthesis is attempted
        sink = await _drive_no_audio(processor, [TextFrame(text="bonjour")])
        # THEN no audio is invented and a no_audio UNAVAILABLE outcome is recorded
        self.assertEqual(sink.audio, [])
        self.assertTrue(session.closed)
        unavailable = [e for e in telemetry.events() if e.name == "tts.unavailable"]
        self.assertTrue(unavailable)
        self.assertEqual(unavailable[0].attributes["error_code"], "no_audio")

    async def test_barge_in_cancels_synthesis_and_closes_session(self):
        # GIVEN a synthesis in flight (first chunk played, more pending on a gate)
        telemetry = TelemetryRecorder()
        session = GatedSession([AudioChunk(b"\x01\x02")])
        processor = _processor(FakeProvider(session), telemetry)
        # WHEN the customer barges in (an InterruptionFrame reaches the processor)
        sink = await _drive_with_interruption(processor, [TextFrame(text="une longue reponse")])
        # THEN only the already-played chunk was emitted, the session is closed (no
        # leaked WebSocket), and an interrupted outcome is recorded (not a failure)
        self.assertEqual(sink.audio, [b"\x01\x02"])
        self.assertTrue(session.closed)
        interrupted = [e for e in telemetry.events() if e.name == "tts.interrupted"]
        self.assertTrue(interrupted)
        self.assertEqual(interrupted[0].attributes["outcome"], "interrupted")
        self.assertIn("elapsed_ms", interrupted[0].attributes)
        self.assertFalse(any(e.name == "tts.failure" for e in telemetry.events()))
        # AND because audio did play, exactly one voice.tts.first_audio span is emitted
        # (carrying the time-to-first-audio, a valid slice sample — never total elapsed)
        spans = [s for s in telemetry.spans() if s.name == TTS_FIRST_AUDIO_SPAN]
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes["outcome"], "interrupted")

    async def test_barge_in_before_any_audio_emits_no_first_audio_span(self):
        # GIVEN a synthesis interrupted before any audio chunk was streamed
        telemetry = TelemetryRecorder()
        session = GatedSession([])
        processor = _processor(FakeProvider(session), telemetry)
        # WHEN the customer barges in before the first audio
        sink = await _drive_with_interruption(processor, [TextFrame(text="reponse")])
        # THEN no audio played and NO first_audio span is emitted (it would skew the
        # tts_first_audio p95), but the interruption is still recorded and cleaned up
        self.assertEqual(sink.audio, [])
        self.assertTrue(session.closed)
        self.assertEqual([s for s in telemetry.spans() if s.name == TTS_FIRST_AUDIO_SPAN], [])
        self.assertTrue(any(e.name == "tts.interrupted" for e in telemetry.events()))


async def _drive_with_interruption(processor: StreamingTtsProcessor, frames) -> _Sink:
    """Start a synthesis, wait for it to be in-flight, then inject an InterruptionFrame
    (barge-in) so Pipecat cancels the processor's task mid-stream."""
    sink = _Sink()
    pipeline = Pipeline([_Source(frames), processor, sink])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from pipecat.frames.frames import EndFrame, InterruptionFrame
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask

        task = PipelineTask(
            pipeline, params=PipelineParams(), enable_rtvi=False,
            enable_turn_tracking=False, cancel_on_idle_timeout=False, check_dangling_tasks=False,
        )
        run = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        deadline = asyncio.get_event_loop().time() + 1.5
        while not sink.audio and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        await task.queue_frames([InterruptionFrame()])
        await asyncio.sleep(0.1)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink


async def _drive_no_audio(processor: StreamingTtsProcessor, frames) -> _Sink:
    """Drive a turn that produces no audio (UNAVAILABLE/FAILED) — end on a short wait."""
    sink = _Sink()
    pipeline = Pipeline([_Source(frames), processor, sink])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from pipecat.frames.frames import EndFrame
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


if __name__ == "__main__":
    unittest.main()
