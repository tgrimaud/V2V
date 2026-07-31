"""Tests for lever 1 — streaming the backend answer to TTS on the first vetted sentence.

Covers TASK-WEB-020: the SSE parser (`parse_sse_events`), the `StreamedAnswerRunner`
(first-sentence-to-push ordering, blocked hand-off, degraded/error mapping, option-A
advisory low confidence, barge-in cancellation with no post-cancel speech and a closed
stream), and the `AnswerProcessor` streaming branch (flag on/off, no filler double-speak).
"""

import asyncio
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from pipecat.frames.frames import TextFrame, TranscriptionFrame  # noqa: E402
from pipecat.tests.utils import run_test  # noqa: E402

from conversation_backend import (  # noqa: E402
    CHUNK,
    DONE,
    ERROR,
    AnswerOutcome,
    AnswerRequest,
    AnswerStreamEvent,
    DEGRADED_FALLBACK_TEXT,
    EmptyTranscriptError,
    StreamControl,
    parse_sse_events,
)
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from voice_pipeline.answer import AnswerProcessor  # noqa: E402
from voice_pipeline.streaming_answer import (  # noqa: E402
    BACKEND_FIRST_TOKEN_SPAN,
    BACKEND_REQUEST_SPAN,
    BACKEND_STREAM_INTERRUPTED_EVENT,
    BACKEND_STREAM_LOW_CONFIDENCE_EVENT,
    BACKEND_STREAMED_EVENT,
    StreamedAnswerRunner,
)


def _request() -> AnswerRequest:
    return AnswerRequest(
        transcript="pourquoi ma facture augmente",
        correlation_id="corr-1",
        conversation_id="conv-1",
        channel="web_voice",
    )


def _envelope() -> SimpleNamespace:
    return SimpleNamespace(channel="web_voice", conversation_id="conv-1", correlation_id="corr-1")


class _ScriptedStreamBackend:
    """Backend whose `answer_stream` yields a fixed list of events (no network)."""

    name = "fake-stream"

    def __init__(self, events: list[AnswerStreamEvent]) -> None:
        self._events = events

    def answer_stream(self, request, control=None):
        if not request.transcript or not request.transcript.strip():
            raise EmptyTranscriptError("nothing to answer")
        yield from self._events


class _BlockingStreamBackend:
    """Yields one chunk then blocks until the control is aborted (barge-in test)."""

    name = "blocking-stream"

    def __init__(self) -> None:
        self.stopped_seen = False

    def answer_stream(self, request, control=None):
        yield AnswerStreamEvent(kind=CHUNK, text="sentence one")
        while control is not None and not control.stopped:
            time.sleep(0.01)
        self.stopped_seen = True


class _RaisingStreamBackend:
    name = "raising-stream"

    def answer_stream(self, request, control=None):
        yield AnswerStreamEvent(kind=CHUNK, text="premiere phrase")
        raise RuntimeError("provider blew up mid-stream")


async def _collect(runner: StreamedAnswerRunner, request: AnswerRequest):
    pushed: list[str] = []

    async def push(text: str) -> None:
        pushed.append(text)

    result = await runner.run(request, push)
    return pushed, result


class SseParserTest(unittest.TestCase):
    def test_parses_chunk_done_and_error_events(self) -> None:
        # GIVEN an SSE stream with a chunk, a terminal done and (separately) an error
        lines = [
            "event:chunk\n",
            'data:{"text":"Bonjour."}\n',
            "\n",
            "event:done\n",
            'data:{"text":"Bonjour.","confidence":0.83,"grounded":true}\n',
            "\n",
        ]
        # WHEN parsed
        events = list(parse_sse_events(lines))
        # THEN the chunk text and the terminal confidence/grounded are recovered
        self.assertEqual(events[0], AnswerStreamEvent(kind=CHUNK, text="Bonjour."))
        self.assertEqual(events[1].kind, DONE)
        self.assertAlmostEqual(events[1].confidence, 0.83)
        self.assertIs(events[1].grounded, True)

    def test_ignores_comments_blank_data_and_malformed_json(self) -> None:
        # GIVEN comment lines, a leading-space value and a malformed data payload
        lines = [
            ": keep-alive\n",
            "event: error\n",
            'data: {"code":"ERR_UPSTREAM","message":"unavailable"}\n',
            "\n",
            "event:done\n",
            "data:{not json}\n",
            "\n",
        ]
        # WHEN parsed
        events = list(parse_sse_events(lines))
        # THEN only the well-formed error event survives (malformed done is skipped)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, ERROR)
        self.assertEqual(events[0].error_code, "ERR_UPSTREAM")

    def test_blank_text_chunk_is_dropped(self) -> None:
        # GIVEN a chunk whose text is blank (never speak empty)
        lines = ['event:chunk\n', 'data:{"text":"   "}\n', "\n"]
        # WHEN parsed -> THEN no event is produced
        self.assertEqual(list(parse_sse_events(lines)), [])


class StreamedAnswerRunnerTest(unittest.IsolatedAsyncioTestCase):
    async def test_pushes_each_sentence_in_order_and_maps_success(self) -> None:
        # GIVEN a stream of two vetted sentences then a grounded done
        backend = _ScriptedStreamBackend(
            [
                AnswerStreamEvent(kind=CHUNK, text="Bonjour."),
                AnswerStreamEvent(kind=CHUNK, text="Votre facture a augmente."),
                AnswerStreamEvent(kind=DONE, text="Bonjour. Votre facture a augmente.", confidence=0.9, grounded=True),
            ]
        )
        telemetry = TelemetryRecorder()
        runner = StreamedAnswerRunner(backend, telemetry, confidence_threshold=0.5)
        # WHEN the turn runs
        pushed, result = await _collect(runner, _request())
        # THEN each sentence is pushed once, in order, and the result is SUCCESS
        self.assertEqual(pushed, ["Bonjour.", "Votre facture a augmente."])
        self.assertIs(result.outcome, AnswerOutcome.SUCCESS)
        self.assertEqual(result.text, "Bonjour. Votre facture a augmente.")
        # AND both US-036 slices are emitted (first_token for sentence 1, request total)
        span_names = [s.name for s in telemetry.spans()]
        self.assertIn(BACKEND_FIRST_TOKEN_SPAN, span_names)
        self.assertIn(BACKEND_REQUEST_SPAN, span_names)
        streamed = next(e for e in telemetry.events() if e.name == BACKEND_STREAMED_EVENT)
        self.assertEqual(streamed.attributes["sentences"], 2)

    async def test_blocked_sentence_handoff_speaks_backend_fallback_and_degrades(self) -> None:
        # GIVEN the backend emits the safe hand-off chunk then a non-grounded done
        backend = _ScriptedStreamBackend(
            [
                AnswerStreamEvent(kind=CHUNK, text="Un conseiller pourra vous aider."),
                AnswerStreamEvent(kind=DONE, text="Un conseiller pourra vous aider.", grounded=False),
            ]
        )
        runner = StreamedAnswerRunner(backend, TelemetryRecorder(), confidence_threshold=0.5)
        # WHEN the turn runs
        pushed, result = await _collect(runner, _request())
        # THEN the hand-off is spoken exactly as the backend sent it (no extra fallback)
        self.assertEqual(pushed, ["Un conseiller pourra vous aider."])
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)

    async def test_error_before_any_chunk_speaks_the_safe_fallback_once(self) -> None:
        # GIVEN the backend fails before any sentence
        backend = _ScriptedStreamBackend(
            [AnswerStreamEvent(kind=ERROR, error_code="ERR_UPSTREAM", error_reason="unavailable")]
        )
        runner = StreamedAnswerRunner(backend, TelemetryRecorder(), confidence_threshold=0.5)
        # WHEN the turn runs
        pushed, result = await _collect(runner, _request())
        # THEN the safe fallback is spoken once and the turn is degraded (no invented text)
        self.assertEqual(pushed, [DEGRADED_FALLBACK_TEXT])
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)
        self.assertEqual(result.error_code, "ERR_UPSTREAM")

    async def test_empty_stream_speaks_the_safe_fallback(self) -> None:
        # GIVEN a stream with no chunk and only a done
        backend = _ScriptedStreamBackend([AnswerStreamEvent(kind=DONE, text="", grounded=True)])
        runner = StreamedAnswerRunner(backend, TelemetryRecorder(), confidence_threshold=0.5)
        # WHEN the turn runs -> THEN the safe fallback is spoken and the turn is degraded
        pushed, result = await _collect(runner, _request())
        self.assertEqual(pushed, [DEGRADED_FALLBACK_TEXT])
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)

    async def test_grounded_low_confidence_stays_spoken_and_logs_advisory(self) -> None:
        # GIVEN a grounded answer below the client confidence floor (option A)
        backend = _ScriptedStreamBackend(
            [
                AnswerStreamEvent(kind=CHUNK, text="Votre forfait a change."),
                AnswerStreamEvent(kind=DONE, text="Votre forfait a change.", confidence=0.2, grounded=True),
            ]
        )
        telemetry = TelemetryRecorder()
        runner = StreamedAnswerRunner(backend, telemetry, confidence_threshold=0.5)
        # WHEN the turn runs
        pushed, result = await _collect(runner, _request())
        # THEN the grounded sentence is still spoken (never un-said) and stays SUCCESS
        self.assertEqual(pushed, ["Votre forfait a change."])
        self.assertIs(result.outcome, AnswerOutcome.SUCCESS)
        # AND an advisory low-confidence event is recorded (not a downgrade)
        self.assertTrue(any(e.name == BACKEND_STREAM_LOW_CONFIDENCE_EVENT for e in telemetry.events()))

    async def test_truncated_stream_without_done_degrades_but_keeps_spoken_text(self) -> None:
        # GIVEN a stream that delivers a vetted sentence then ends with no done/error
        backend = _ScriptedStreamBackend([AnswerStreamEvent(kind=CHUNK, text="Debut de reponse.")])
        runner = StreamedAnswerRunner(backend, TelemetryRecorder(), confidence_threshold=0.5)
        # WHEN the turn runs
        pushed, result = await _collect(runner, _request())
        # THEN the vetted sentence stays spoken (never re-fabricated) but the turn degrades
        self.assertEqual(pushed, ["Debut de reponse."])
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)
        self.assertEqual(result.text, "Debut de reponse.")

    async def test_empty_transcript_stays_silent(self) -> None:
        # GIVEN an empty transcript (nothing to answer)
        backend = _ScriptedStreamBackend([AnswerStreamEvent(kind=CHUNK, text="x")])
        runner = StreamedAnswerRunner(backend, TelemetryRecorder(), confidence_threshold=0.5)
        empty = AnswerRequest(transcript="   ", correlation_id="c", conversation_id="v", channel="web_voice")
        pushed: list[str] = []

        async def push(text: str) -> None:
            pushed.append(text)

        # WHEN the turn runs -> THEN EmptyTranscriptError propagates and nothing is spoken
        with self.assertRaises(EmptyTranscriptError):
            await runner.run(empty, push)
        self.assertEqual(pushed, [])

    async def test_raising_adapter_degrades_safely(self) -> None:
        # GIVEN an adapter that raises mid-stream after one chunk
        runner = StreamedAnswerRunner(_RaisingStreamBackend(), TelemetryRecorder(), confidence_threshold=0.5)
        # WHEN the turn runs
        pushed, result = await _collect(runner, _request())
        # THEN the already-vetted sentence stays spoken and the turn degrades (no crash)
        self.assertEqual(pushed, ["premiere phrase"])
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)

    async def test_barge_in_cancels_stream_no_post_cancel_speech(self) -> None:
        # GIVEN a stream that blocks after the first sentence
        backend = _BlockingStreamBackend()
        telemetry = TelemetryRecorder()
        runner = StreamedAnswerRunner(backend, telemetry, confidence_threshold=0.5)
        pushed: list[str] = []
        first = asyncio.Event()

        async def push(text: str) -> None:
            pushed.append(text)
            first.set()

        task = asyncio.create_task(runner.run(_request(), push))
        await asyncio.wait_for(first.wait(), 1.0)
        # WHEN the turn is cancelled (barge-in) after the first sentence
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        # THEN only the first sentence was spoken and the stream was aborted (socket closed)
        self.assertEqual(pushed, ["sentence one"])
        await asyncio.sleep(0.05)
        self.assertTrue(backend.stopped_seen)
        # AND an interrupted outcome is recorded
        self.assertTrue(any(e.name == BACKEND_STREAM_INTERRUPTED_EVENT for e in telemetry.events()))


class AnswerProcessorStreamingTest(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_flag_pushes_one_frame_per_sentence(self) -> None:
        # GIVEN a streaming backend and the streaming flag on
        backend = _ScriptedStreamBackend(
            [
                AnswerStreamEvent(kind=CHUNK, text="Bonjour."),
                AnswerStreamEvent(kind=CHUNK, text="Voici la reponse."),
                AnswerStreamEvent(kind=DONE, text="Bonjour. Voici la reponse.", confidence=0.9, grounded=True),
            ]
        )
        processor = AnswerProcessor(backend, _envelope(), backend_stream=True, filler_enabled_flag=False)
        # WHEN a transcription flows through
        down, _up = await run_test(
            processor,
            frames_to_send=[TranscriptionFrame(text="pourquoi ma facture augmente", user_id="u", timestamp="")],
        )
        # THEN one plain TextFrame per vetted sentence is emitted, in order
        plain = [f.text for f in down if type(f) is TextFrame]
        self.assertEqual(plain, ["Bonjour.", "Voici la reponse."])
        self.assertIs(processor.result.outcome, AnswerOutcome.SUCCESS)

    async def test_streaming_flag_off_does_not_take_streaming_path(self) -> None:
        # GIVEN a streaming-capable backend but the flag OFF
        backend = _ScriptedStreamBackend([AnswerStreamEvent(kind=CHUNK, text="x")])
        processor = AnswerProcessor(backend, _envelope(), backend_stream=False, filler_enabled_flag=False)
        # THEN the streaming path is not taken (the safe blocking path stays the default)
        self.assertFalse(processor._stream_this_turn())

    async def test_backend_without_answer_stream_falls_back_transparently(self) -> None:
        # GIVEN the flag ON but a backend that cannot stream (no answer_stream)
        blocking_only = SimpleNamespace(name="no-stream", answer=lambda req: None)
        processor = AnswerProcessor(blocking_only, _envelope(), backend_stream=True, filler_enabled_flag=False)
        # THEN the streaming path is transparently skipped (capability-gated)
        self.assertFalse(processor._stream_this_turn())


if __name__ == "__main__":
    unittest.main()
