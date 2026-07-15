import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation_backend import (  # noqa: E402
    AnswerOutcome,
    AnswerRequest,
    AnswerResult,
    BackendAnswerPort,
    EmptyTranscriptError,
)


class _StubEnvelope:
    """Structural stand-in for web_voice.ChannelEnvelope (kept out of the import graph)."""

    channel = "web_voice"
    conversation_id = "conv-1"
    correlation_id = "corr-1"


class _FakeBackend:
    """Minimal port implementation proving the protocol is usable structurally."""

    name = "fake-backend"

    def __init__(self, result: AnswerResult) -> None:
        self._result = result

    def answer(self, request: AnswerRequest) -> AnswerResult:
        return self._result


class AnswerOutcomeTest(unittest.TestCase):
    def test_outcomes_expose_stable_string_values(self) -> None:
        # GIVEN the answer outcome enum
        # WHEN its members are read
        # THEN the three stable values exist (mirrors STT/TTS outcome vocabularies)
        self.assertEqual(AnswerOutcome.SUCCESS.value, "success")
        self.assertEqual(AnswerOutcome.DEGRADED.value, "degraded")
        self.assertEqual(AnswerOutcome.UNAVAILABLE.value, "unavailable")


class AnswerRequestTest(unittest.TestCase):
    def test_from_envelope_copies_traceability_fields(self) -> None:
        # GIVEN a transcript and a channel-envelope-like object
        envelope = _StubEnvelope()

        # WHEN a request is built from it
        request = AnswerRequest.from_envelope("pourquoi ma facture augmente", envelope)

        # THEN the transcript and traceability fields are carried through
        self.assertEqual(request.transcript, "pourquoi ma facture augmente")
        self.assertEqual(request.channel, "web_voice")
        self.assertEqual(request.conversation_id, "conv-1")
        self.assertEqual(request.correlation_id, "corr-1")

    def test_to_dict_exposes_transcript_length_not_the_transcript(self) -> None:
        # GIVEN a request carrying potentially personal transcript content
        request = AnswerRequest(
            transcript="mon numero est 0612345678",
            correlation_id="corr-1",
            conversation_id="conv-1",
            channel="web_voice",
        )

        # WHEN it is serialized for telemetry/QA
        payload = request.to_dict()

        # THEN only the character count is exposed, never the raw transcript
        self.assertEqual(payload["transcript_chars"], len("mon numero est 0612345678"))
        self.assertNotIn("transcript", payload)
        self.assertNotIn("0612345678", str(payload))


class AnswerResultTest(unittest.TestCase):
    def test_is_success_only_for_success_outcome(self) -> None:
        # GIVEN results with each outcome
        success = AnswerResult(text="ok", provider="p", outcome=AnswerOutcome.SUCCESS, correlation_id="c")
        degraded = AnswerResult(text="", provider="p", outcome=AnswerOutcome.DEGRADED, correlation_id="c")

        # WHEN is_success is read
        # THEN only the SUCCESS outcome is truthy
        self.assertTrue(success.is_success)
        self.assertFalse(degraded.is_success)

    def test_to_dict_exposes_text_length_not_the_text(self) -> None:
        # GIVEN a result whose text may carry customer-visible content
        result = AnswerResult(
            text="Votre facture a augmente de 5 euros",
            provider="stub-backend",
            outcome=AnswerOutcome.SUCCESS,
            correlation_id="corr-1",
            confidence=0.9,
            duration_ms=12.3456,
        )

        # WHEN it is serialized for telemetry/QA
        payload = result.to_dict()

        # THEN the outcome/metadata are present and only the text length is exposed
        self.assertEqual(payload["outcome"], "success")
        self.assertEqual(payload["provider"], "stub-backend")
        self.assertEqual(payload["correlation_id"], "corr-1")
        self.assertEqual(payload["confidence"], 0.9)
        self.assertEqual(payload["duration_ms"], 12.346)
        self.assertEqual(payload["text_chars"], len("Votre facture a augmente de 5 euros"))
        self.assertNotIn("text", payload)
        self.assertNotIn("facture", str(payload))

    def test_degraded_result_carries_reason_and_no_success(self) -> None:
        # GIVEN a degraded result with a reason
        result = AnswerResult(
            text="Je ne peux pas repondre pour le moment",
            provider="stub-backend",
            outcome=AnswerOutcome.DEGRADED,
            correlation_id="corr-1",
            degraded_reason="backend_unavailable",
        )

        # WHEN it is serialized
        payload = result.to_dict()

        # THEN the degraded reason is reported and it is not a success
        self.assertFalse(result.is_success)
        self.assertEqual(payload["degraded_reason"], "backend_unavailable")


class BackendAnswerPortTest(unittest.TestCase):
    def test_a_structural_implementation_satisfies_the_port(self) -> None:
        # GIVEN a fake backend implementing name + answer(request)
        expected = AnswerResult(text="ok", provider="fake-backend", outcome=AnswerOutcome.SUCCESS, correlation_id="c")
        backend: BackendAnswerPort = _FakeBackend(expected)
        request = AnswerRequest.from_envelope("bonjour", _StubEnvelope())

        # WHEN it answers a request through the port surface
        result = backend.answer(request)

        # THEN the port contract is usable and returns the expected result
        self.assertEqual(backend.name, "fake-backend")
        self.assertIs(result, expected)


class EmptyTranscriptErrorTest(unittest.TestCase):
    def test_is_a_runtime_error(self) -> None:
        # GIVEN the empty-transcript signal
        # WHEN it is raised
        # THEN it is a RuntimeError so callers can map it to an UNAVAILABLE outcome
        with self.assertRaises(RuntimeError):
            raise EmptyTranscriptError("nothing to answer")


if __name__ == "__main__":
    unittest.main()
