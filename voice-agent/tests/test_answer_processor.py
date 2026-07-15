"""Tests for the backend answer processor (TASK-WEB-003-D).

`AnswerProcessor` replaces the echo step: it turns an STT `TranscriptionFrame` into
a plain `TextFrame` carrying the backend's answer, and emits a `backend.request`
telemetry span with only lengths (never the raw transcript or answer).
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from pipecat.frames.frames import TextFrame, TranscriptionFrame  # noqa: E402
from pipecat.tests.utils import run_test  # noqa: E402

from conversation_backend import (  # noqa: E402
    AnswerOutcome,
    AnswerRequest,
    AnswerResult,
    EmptyTranscriptError,
)
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from voice_pipeline.answer import (  # noqa: E402
    BACKEND_FIRST_TOKEN_SPAN,
    BACKEND_REQUEST_SPAN,
    AnswerProcessor,
    answer_with_telemetry,
)


def _envelope() -> SimpleNamespace:
    return SimpleNamespace(channel="web_voice", conversation_id="conv-1", correlation_id="corr-1")


class _FakeBackend:
    name = "fake-backend"

    def __init__(self, text: str = "voici la reponse", outcome: AnswerOutcome = AnswerOutcome.SUCCESS) -> None:
        self._text = text
        self._outcome = outcome
        self.requests: list[AnswerRequest] = []

    def answer(self, request: AnswerRequest) -> AnswerResult:
        self.requests.append(request)
        return AnswerResult(
            text=self._text,
            provider=self.name,
            outcome=self._outcome,
            correlation_id=request.correlation_id,
        )


class _RaisingBackend:
    name = "raising-backend"

    def answer(self, request: AnswerRequest) -> AnswerResult:
        raise EmptyTranscriptError("nothing to answer")


class AnswerProcessorTest(unittest.IsolatedAsyncioTestCase):
    async def test_transcription_becomes_the_backend_answer_text(self) -> None:
        # GIVEN an answer processor over a backend that returns a fixed answer
        backend = _FakeBackend(text="voici la reponse")
        processor = AnswerProcessor(backend, _envelope())
        # WHEN a transcription flows through
        down, _up = await run_test(
            processor,
            frames_to_send=[TranscriptionFrame(text="pourquoi ma facture augmente", user_id="u", timestamp="")],
        )
        # THEN a plain TextFrame carrying the ANSWER is emitted (not the transcript)
        plain = [f for f in down if isinstance(f, TextFrame) and not isinstance(f, TranscriptionFrame)]
        self.assertEqual(len(plain), 1)
        self.assertEqual(plain[0].text, "voici la reponse")
        self.assertEqual(backend.requests[0].transcript, "pourquoi ma facture augmente")
        self.assertIs(processor.result.outcome, AnswerOutcome.SUCCESS)

    async def test_unavailable_answer_pushes_no_text(self) -> None:
        # GIVEN a backend returning UNAVAILABLE with empty text
        processor = AnswerProcessor(_FakeBackend(text="", outcome=AnswerOutcome.UNAVAILABLE), _envelope())
        # WHEN a transcription flows through
        down, _up = await run_test(
            processor,
            frames_to_send=[TranscriptionFrame(text="bonjour", user_id="u", timestamp="")],
        )
        # THEN no plain TextFrame is emitted (never invent a spoken turn)
        plain = [f for f in down if isinstance(f, TextFrame) and not isinstance(f, TranscriptionFrame)]
        self.assertEqual(plain, [])

    async def test_empty_transcript_error_is_swallowed_without_output(self) -> None:
        # GIVEN a backend that signals "nothing to answer"
        processor = AnswerProcessor(_RaisingBackend(), _envelope())
        # WHEN a transcription flows through
        down, _up = await run_test(
            processor,
            frames_to_send=[TranscriptionFrame(text="   ", user_id="u", timestamp="")],
        )
        # THEN no text flows downstream and no answer is recorded
        plain = [f for f in down if isinstance(f, TextFrame) and not isinstance(f, TranscriptionFrame)]
        self.assertEqual(plain, [])
        self.assertIsNone(processor.result)


class AnswerTelemetryTest(unittest.TestCase):
    def test_emits_backend_span_and_event_with_lengths_only(self) -> None:
        # GIVEN a telemetry recorder and a request carrying personal transcript content
        telemetry = TelemetryRecorder()
        request = AnswerRequest(
            transcript="mon numero est 0612345678",
            correlation_id="corr-1",
            conversation_id="conv-1",
            channel="web_voice",
        )
        # WHEN the backend is called through the telemetry helper
        result = answer_with_telemetry(_FakeBackend(text="reponse"), request, telemetry)

        # THEN both backend spans are emitted with correlation id, provider and outcome
        span_names = {s.name for s in telemetry.spans()}
        self.assertIn(BACKEND_FIRST_TOKEN_SPAN, span_names)
        self.assertIn(BACKEND_REQUEST_SPAN, span_names)
        span = next(s for s in telemetry.spans() if s.name == BACKEND_REQUEST_SPAN)
        self.assertEqual(span.attributes["correlation_id"], "corr-1")
        self.assertEqual(span.attributes["provider"], "fake-backend")
        self.assertEqual(span.attributes["outcome"], "success")
        self.assertEqual(span.attributes["answer_chars"], len("reponse"))
        # AND no raw transcript or answer text leaks into telemetry
        self.assertNotIn("0612345678", str([s.attributes for s in telemetry.spans()]))
        self.assertNotIn("reponse", str([s.attributes for s in telemetry.spans()]))
        self.assertEqual(result.text, "reponse")

    def test_no_telemetry_is_optional(self) -> None:
        # GIVEN no telemetry recorder
        request = AnswerRequest(transcript="bonjour", correlation_id="c", conversation_id="conv", channel="web_voice")
        # WHEN the helper is called with telemetry=None
        result = answer_with_telemetry(_FakeBackend(text="ok"), request, None)
        # THEN it still returns the answer without raising
        self.assertEqual(result.text, "ok")


if __name__ == "__main__":
    unittest.main()
