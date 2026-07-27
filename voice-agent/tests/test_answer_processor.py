"""Tests for the backend answer processor (TASK-WEB-003-D).

`AnswerProcessor` replaces the echo step: it turns an STT `TranscriptionFrame` into
a plain `TextFrame` carrying the backend's answer, and emits a `backend.request`
telemetry span with only lengths (never the raw transcript or answer).
"""

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from pipecat.frames.frames import TextFrame, TranscriptionFrame  # noqa: E402
from pipecat.tests.utils import run_test  # noqa: E402

from conversation_backend import (  # noqa: E402
    DEGRADED_FALLBACK_TEXT,
    AnswerOutcome,
    AnswerRequest,
    AnswerResult,
    EmptyTranscriptError,
)
from conversation_backend import DEFAULT_CONFIDENCE_THRESHOLD  # noqa: E402
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from voice_pipeline.answer import (  # noqa: E402
    BACKEND_FIRST_TOKEN_SPAN,
    BACKEND_REQUEST_SPAN,
    CONFIDENCE_THRESHOLD_ENV_VAR,
    AnswerProcessor,
    answer_with_telemetry,
    resolve_confidence_threshold,
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


class _UnavailableBackend:
    """Backend that fails with a fault carrying a secret-looking token in its message."""

    name = "http-backend"

    def answer(self, request: AnswerRequest) -> AnswerResult:
        raise RuntimeError("connection refused to /srv/secret-customer.wav token sk-abcdef123456")


class _LowConfidenceBackend:
    name = "unsure-backend"

    def __init__(self, confidence: float) -> None:
        self._confidence = confidence

    def answer(self, request: AnswerRequest) -> AnswerResult:
        return AnswerResult(
            text="votre facture est de 42 euros",
            provider=self.name,
            outcome=AnswerOutcome.SUCCESS,
            correlation_id=request.correlation_id,
            confidence=self._confidence,
        )


def _request() -> AnswerRequest:
    return AnswerRequest(
        transcript="pourquoi ma facture augmente",
        correlation_id="corr-1",
        conversation_id="conv-1",
        channel="web_voice",
    )


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

    async def test_backend_failure_speaks_the_safe_fallback(self) -> None:
        # GIVEN a backend that fails (unavailable), not an empty transcript
        processor = AnswerProcessor(_UnavailableBackend(), _envelope())
        # WHEN a transcription flows through
        down, _up = await run_test(
            processor,
            frames_to_send=[TranscriptionFrame(text="pourquoi ma facture augmente", user_id="u", timestamp="")],
        )
        # THEN the safe fallback is spoken (degraded), never a crash and never invented content
        plain = [f for f in down if isinstance(f, TextFrame) and not isinstance(f, TranscriptionFrame)]
        self.assertEqual(len(plain), 1)
        self.assertEqual(plain[0].text, DEGRADED_FALLBACK_TEXT)
        self.assertIs(processor.result.outcome, AnswerOutcome.DEGRADED)


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


class DegradedModeTest(unittest.TestCase):
    def test_backend_failure_returns_safe_fallback_never_raises(self) -> None:
        # GIVEN a backend that raises an unexpected fault
        telemetry = TelemetryRecorder()
        # WHEN the helper is called
        result = answer_with_telemetry(_UnavailableBackend(), _request(), telemetry)
        # THEN a DEGRADED result carrying the safe fallback text is returned (no raise)
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)
        self.assertEqual(result.text, DEGRADED_FALLBACK_TEXT)
        self.assertEqual(result.degraded_reason, "backend_unavailable")
        self.assertEqual(result.provider, "http-backend")

    def test_backend_failure_sanitizes_the_error_and_leaks_no_secret(self) -> None:
        # GIVEN a backend whose fault message carries a path, filename and secret token
        telemetry = TelemetryRecorder()
        # WHEN the helper degrades
        result = answer_with_telemetry(_UnavailableBackend(), _request(), telemetry)
        # THEN the error is sanitized: a stable code + a redacted reason, no raw secret
        self.assertEqual(result.error_code, "backend_error")
        blob = result.error_reason + str([s.attributes for s in telemetry.spans()])
        self.assertNotIn("secret-customer.wav", blob)
        self.assertNotIn("sk-abcdef123456", blob)
        self.assertNotIn("/srv/", blob)

    def test_degraded_telemetry_is_observable_with_lengths_only(self) -> None:
        # GIVEN a failing backend and a recorder
        telemetry = TelemetryRecorder()
        # WHEN the helper degrades
        answer_with_telemetry(_UnavailableBackend(), _request(), telemetry)
        # THEN both backend spans carry the degraded outcome + flag, and a warning log is emitted
        span = next(s for s in telemetry.spans() if s.name == BACKEND_REQUEST_SPAN)
        self.assertEqual(span.attributes["outcome"], "degraded")
        self.assertTrue(span.attributes["degraded"])
        self.assertEqual(span.attributes["degraded_reason"], "backend_unavailable")
        self.assertEqual(span.attributes["answer_chars"], len(DEGRADED_FALLBACK_TEXT))
        self.assertTrue(any(log.level == "warning" for log in telemetry.logs()))

    def test_low_confidence_answer_is_replaced_by_the_safe_fallback(self) -> None:
        # GIVEN a confident-looking answer with a low confidence score (below threshold)
        telemetry = TelemetryRecorder()
        # WHEN the helper applies the confidence policy
        result = answer_with_telemetry(_LowConfidenceBackend(confidence=0.2), _request(), telemetry)
        # THEN the low-confidence content (with an amount!) is never spoken; the fallback is
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)
        self.assertEqual(result.text, DEGRADED_FALLBACK_TEXT)
        self.assertEqual(result.degraded_reason, "low_confidence")
        self.assertNotIn("42", result.text)

    def test_high_confidence_answer_is_kept(self) -> None:
        # GIVEN an answer whose confidence is above the threshold
        # WHEN the helper applies the confidence policy
        result = answer_with_telemetry(_LowConfidenceBackend(confidence=0.9), _request(), None)
        # THEN the real answer is kept (not degraded)
        self.assertIs(result.outcome, AnswerOutcome.SUCCESS)
        self.assertEqual(result.text, "votre facture est de 42 euros")

    def test_safe_fallback_text_contains_no_digit(self) -> None:
        # GIVEN the safe fallback text (DEC-002: never state a fabricated amount)
        # THEN it carries no digit or currency figure
        self.assertFalse(any(ch.isdigit() for ch in DEGRADED_FALLBACK_TEXT))

    def test_confidence_policy_uses_an_explicit_higher_threshold(self) -> None:
        # GIVEN an answer at 0.6 confidence and an explicit floor raised to 0.7 (RF-022)
        telemetry = TelemetryRecorder()
        # WHEN the helper applies the confidence policy with the raised floor
        result = answer_with_telemetry(
            _LowConfidenceBackend(confidence=0.6), _request(), telemetry, confidence_threshold=0.7
        )
        # THEN the 0.6 answer is now below the floor and replaced by the safe fallback
        self.assertIs(result.outcome, AnswerOutcome.DEGRADED)
        self.assertEqual(result.degraded_reason, "low_confidence")


class ResolveConfidenceThresholdTest(unittest.TestCase):
    """RF-022: env-tunable degraded-mode confidence floor (`VOICE_BACKEND_CONFIDENCE_THRESHOLD`)."""

    def setUp(self) -> None:
        self._saved = os.environ.pop(CONFIDENCE_THRESHOLD_ENV_VAR, None)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(CONFIDENCE_THRESHOLD_ENV_VAR, None)
        else:
            os.environ[CONFIDENCE_THRESHOLD_ENV_VAR] = self._saved

    def test_unset_env_falls_back_to_the_default(self) -> None:
        # GIVEN no override set -> THEN the shared default floor is used
        self.assertEqual(resolve_confidence_threshold(), DEFAULT_CONFIDENCE_THRESHOLD)

    def test_valid_override_is_honoured(self) -> None:
        # GIVEN a valid in-range override
        os.environ[CONFIDENCE_THRESHOLD_ENV_VAR] = "0.72"
        # THEN it wins over the default
        self.assertAlmostEqual(resolve_confidence_threshold(), 0.72)

    def test_boundaries_zero_and_one_are_accepted(self) -> None:
        # GIVEN the inclusive [0, 1] boundaries
        os.environ[CONFIDENCE_THRESHOLD_ENV_VAR] = "0"
        self.assertEqual(resolve_confidence_threshold(), 0.0)
        os.environ[CONFIDENCE_THRESHOLD_ENV_VAR] = "1"
        self.assertEqual(resolve_confidence_threshold(), 1.0)

    def test_non_numeric_override_degrades_to_the_default(self) -> None:
        # GIVEN a non-numeric value -> THEN parsing fails safe to the default
        os.environ[CONFIDENCE_THRESHOLD_ENV_VAR] = "high"
        self.assertEqual(resolve_confidence_threshold(), DEFAULT_CONFIDENCE_THRESHOLD)

    def test_out_of_range_override_degrades_to_the_default(self) -> None:
        # GIVEN values outside [0, 1] (a probability floor cannot be > 1 or < 0)
        os.environ[CONFIDENCE_THRESHOLD_ENV_VAR] = "1.5"
        self.assertEqual(resolve_confidence_threshold(), DEFAULT_CONFIDENCE_THRESHOLD)
        os.environ[CONFIDENCE_THRESHOLD_ENV_VAR] = "-0.1"
        self.assertEqual(resolve_confidence_threshold(), DEFAULT_CONFIDENCE_THRESHOLD)

    def test_processor_resolves_the_env_threshold_at_construction(self) -> None:
        # GIVEN the env override set before the processor is built
        os.environ[CONFIDENCE_THRESHOLD_ENV_VAR] = "0.8"
        processor = AnswerProcessor(_FakeBackend(), _envelope())
        # THEN the processor adopts the env floor (explicit arg still overrides it)
        self.assertAlmostEqual(processor._confidence_threshold, 0.8)
        explicit = AnswerProcessor(_FakeBackend(), _envelope(), confidence_threshold=0.55)
        self.assertAlmostEqual(explicit._confidence_threshold, 0.55)


if __name__ == "__main__":
    unittest.main()
