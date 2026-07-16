"""Unit tests for the client-safe voice error body (TASK-WEB-006, RF-013)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_voice.error_response import (  # noqa: E402
    DEFAULT_ERROR_CODE,
    GENERIC_VOICE_ERROR,
    client_error_body,
)


class ClientErrorBodyTest(unittest.TestCase):
    def test_carries_stable_code_correlation_and_generic_message(self) -> None:
        # GIVEN a failed turn with a stable code and correlation id
        # WHEN the client-safe body is built
        body = client_error_body("stt_error", "corr-1")

        # THEN it exposes only code + correlation id + a generic message
        self.assertEqual(body["outcome"], "failed")
        self.assertEqual(body["error_code"], "stt_error")
        self.assertEqual(body["correlation_id"], "corr-1")
        self.assertEqual(body["message"], GENERIC_VOICE_ERROR)

    def test_never_includes_a_raw_error_reason_field(self) -> None:
        # GIVEN any failed turn
        body = client_error_body("tts_error", "corr-2")

        # THEN the raw provider reason field is absent from the body entirely
        self.assertNotIn("error_reason", body)
        self.assertNotIn("provider", body)

    def test_falls_back_to_a_default_code_when_none(self) -> None:
        # GIVEN a result that carried no error code (defensive)
        body = client_error_body(None, "corr-3")

        # THEN a stable default code is used, never None
        self.assertEqual(body["error_code"], DEFAULT_ERROR_CODE)
        self.assertEqual(body["message"], GENERIC_VOICE_ERROR)

    def test_uses_a_client_actionable_message_for_known_codes(self) -> None:
        # GIVEN a client-actionable code
        body = client_error_body("no_speech", "corr-4")

        # THEN a specific, author-controlled message is returned (still no provider text)
        self.assertNotEqual(body["message"], GENERIC_VOICE_ERROR)
        self.assertIn("speech", body["message"].lower())

    def test_preserves_a_non_failed_outcome(self) -> None:
        # GIVEN an UNAVAILABLE turn (e.g. empty text)
        body = client_error_body("empty_text", "corr-5", outcome="unavailable")

        # THEN the outcome is carried through unchanged
        self.assertEqual(body["outcome"], "unavailable")


if __name__ == "__main__":
    unittest.main()
