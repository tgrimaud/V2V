import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation_backend import (  # noqa: E402
    AnswerOutcome,
    AnswerRequest,
    BackendAnswerPort,
    EmptyTranscriptError,
    StubBackendAdapter,
)


def _request(transcript: str) -> AnswerRequest:
    return AnswerRequest(
        transcript=transcript,
        correlation_id="corr-1",
        conversation_id="conv-1",
        channel="web_voice",
    )


class StubBackendAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = StubBackendAdapter()

    def test_satisfies_the_backend_answer_port(self) -> None:
        # GIVEN the stub adapter
        # WHEN it is used through the port surface
        backend: BackendAnswerPort = self.adapter
        # THEN it exposes the stable provider name
        self.assertEqual(backend.name, "stub-backend")

    def test_answer_returns_success_with_neutral_text(self) -> None:
        # GIVEN a plausible billing question
        # WHEN the stub answers it
        result = self.adapter.answer(_request("pourquoi ma facture augmente"))

        # THEN it is a successful turn carrying a non-empty spoken text
        self.assertIs(result.outcome, AnswerOutcome.SUCCESS)
        self.assertTrue(result.is_success)
        self.assertTrue(result.text.strip())
        self.assertEqual(result.provider, "stub-backend")

    def test_answer_never_fabricates_an_amount_or_invoice_detail(self) -> None:
        # GIVEN several billing-flavored transcripts that could tempt a fabricated amount
        transcripts = [
            "combien je paye ce mois",
            "ma facture est de combien",
            "pourquoi 5 euros de plus",
        ]

        for transcript in transcripts:
            with self.subTest(transcript=transcript):
                # WHEN the stub answers
                text = self.adapter.answer(_request(transcript)).text

                # THEN the response carries no digit and no currency symbol,
                # so it cannot state an invented amount (DEC-002).
                self.assertFalse(any(ch.isdigit() for ch in text), text)
                self.assertNotIn("€", text)

    def test_answer_is_deterministic(self) -> None:
        # GIVEN the same transcript answered twice
        first = self.adapter.answer(_request("bonjour")).text
        second = self.adapter.answer(_request("bonjour")).text

        # THEN the offline stub returns the exact same text (reproducible for tests)
        self.assertEqual(first, second)

    def test_answer_propagates_correlation_id_and_declares_no_confidence(self) -> None:
        # GIVEN a request carrying a correlation id
        result = self.adapter.answer(_request("bonjour"))

        # THEN the correlation id flows through for end-to-end tracing (TASK-WEB-003-E)
        self.assertEqual(result.correlation_id, "corr-1")
        # AND the stub does not fabricate a confidence score it cannot compute
        self.assertIsNone(result.confidence)

    def test_empty_transcript_raises_empty_transcript_error(self) -> None:
        # GIVEN transcripts with nothing to answer
        for transcript in ["", "   ", "\n\t "]:
            with self.subTest(transcript=repr(transcript)):
                # WHEN the stub is asked to answer
                # THEN it signals UNAVAILABLE via EmptyTranscriptError, never a fabricated turn
                with self.assertRaises(EmptyTranscriptError):
                    self.adapter.answer(_request(transcript))


if __name__ == "__main__":
    unittest.main()
