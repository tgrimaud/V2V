import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stt_validation.sanitization import sanitize_error  # noqa: E402


class ReasonCodeTest(unittest.TestCase):
    def test_maps_known_exception_types_to_stable_codes(self) -> None:
        self.assertEqual(sanitize_error(FileNotFoundError("x")).reason_code, "fixture_missing")
        self.assertEqual(sanitize_error(ValueError("x")).reason_code, "invalid_fixture")
        self.assertEqual(sanitize_error(TimeoutError("x")).reason_code, "stt_timeout")

    def test_unknown_exception_falls_back_to_generic_code(self) -> None:
        self.assertEqual(sanitize_error(RuntimeError("x")).reason_code, "stt_error")


class RedactionTest(unittest.TestCase):
    def test_path_token_is_redacted(self) -> None:
        result = sanitize_error(FileNotFoundError("missing /var/data/secret-customer.wav here"))
        self.assertIn("<redacted-path>", result.reason)
        self.assertNotIn("secret-customer", result.reason)

    def test_bare_filename_without_separator_is_redacted(self) -> None:
        result = sanitize_error(ValueError("could not decode secret-customer.wav for user"))
        self.assertIn("<redacted-file>", result.reason)
        self.assertNotIn("secret-customer", result.reason)

    def test_bare_filename_with_trailing_punctuation_is_redacted(self) -> None:
        result = sanitize_error(ValueError("failed on recording.mp3, aborting"))
        self.assertIn("<redacted-file>", result.reason)
        self.assertNotIn("recording.mp3", result.reason)

    def test_uuid_identifier_is_redacted(self) -> None:
        result = sanitize_error(RuntimeError("session 550e8400-e29b-41d4-a716-446655440000 failed"))
        self.assertIn("<redacted-id>", result.reason)
        self.assertNotIn("550e8400", result.reason)

    def test_secret_prefixed_token_is_redacted(self) -> None:
        result = sanitize_error(RuntimeError("auth rejected key gsk_live_abc123DEF456 invalid"))
        self.assertIn("<redacted-id>", result.reason)
        self.assertNotIn("gsk_live_abc123DEF456", result.reason)

    def test_long_digit_run_is_redacted(self) -> None:
        result = sanitize_error(RuntimeError("account 0612345678 not found"))
        self.assertIn("<redacted-id>", result.reason)
        self.assertNotIn("0612345678", result.reason)

    def test_mixed_alphanumeric_customer_id_is_redacted(self) -> None:
        result = sanitize_error(RuntimeError("customer CUST0009812 blocked"))
        self.assertIn("<redacted-id>", result.reason)
        self.assertNotIn("CUST0009812", result.reason)

    def test_plain_words_and_short_numbers_are_preserved(self) -> None:
        result = sanitize_error(RuntimeError("HTTP 401 unauthorized, insufficient credits"))
        self.assertEqual(result.reason, "HTTP 401 unauthorized, insufficient credits")

    def test_plain_date_is_preserved(self) -> None:
        result = sanitize_error(RuntimeError("run 2026-07-10 aborted"))
        self.assertIn("2026-07-10", result.reason)

    def test_no_speech_message_is_preserved(self) -> None:
        result = sanitize_error(RuntimeError("Gradium STT recognized no speech in the audio"))
        self.assertEqual(result.reason, "Gradium STT recognized no speech in the audio")

    def test_reason_is_length_capped(self) -> None:
        result = sanitize_error(RuntimeError("word " * 100))
        self.assertLessEqual(len(result.reason), 163)
        self.assertTrue(result.reason.endswith("..."))


if __name__ == "__main__":
    unittest.main()
