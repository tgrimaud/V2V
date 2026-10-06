"""TASK-OBS-002 — structured JSON logging for the voice runtime."""

import io
import json
import logging
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_common.log_context import correlation_id_scope  # noqa: E402
from voice_common.logging_config import (  # noqa: E402
    JsonLogFormatter,
    SanitizingTextFormatter,
    configure_logging,
)


def _record(msg: str, *, level: int = logging.INFO, name: str = "web_voice.test", exc_info=None):
    return logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1, msg=msg, args=(), exc_info=exc_info
    )


class JsonLogFormatterTest(unittest.TestCase):
    def test_emits_fixed_json_shape(self) -> None:
        # GIVEN the JSON formatter and a plain info record
        formatter = JsonLogFormatter()
        # WHEN it formats the record
        payload = json.loads(formatter.format(_record("bridge started")))
        # THEN the stable ingestion keys are present
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "web_voice.test")
        self.assertEqual(payload["message"], "bridge started")
        self.assertIn("timestamp", payload)
        # AND no correlation_id key when none is in scope
        self.assertNotIn("correlation_id", payload)

    def test_stamps_correlation_id_from_context(self) -> None:
        # GIVEN a correlation id bound to the current context
        formatter = JsonLogFormatter()
        with correlation_id_scope("corr-42"):
            payload = json.loads(formatter.format(_record("turn done")))
        # THEN it is stamped on the line
        self.assertEqual(payload["correlation_id"], "corr-42")

    def test_sanitizes_secret_and_path_tokens_in_message(self) -> None:
        # GIVEN a message carrying a secret-prefixed token and a filesystem path
        formatter = JsonLogFormatter()
        payload = json.loads(
            formatter.format(_record("auth failed key=sk-abc123def456 file /etc/voice/secret.env"))
        )
        # THEN neither the secret nor the path survive in the emitted line
        self.assertNotIn("sk-abc123def456", payload["message"])
        self.assertNotIn("/etc/voice/secret.env", payload["message"])
        self.assertIn("<redacted-id>", payload["message"])
        self.assertIn("<redacted-path>", payload["message"])
        # AND ordinary words are kept readable
        self.assertIn("auth", payload["message"])

    def test_includes_sanitized_exception(self) -> None:
        # GIVEN a record carrying exception info with a sensitive token
        formatter = JsonLogFormatter()
        try:
            raise ValueError("bad token sk-topsecret9999")
        except ValueError:
            record = _record("stt failure", level=logging.ERROR, exc_info=sys.exc_info())
        payload = json.loads(formatter.format(record))
        # THEN the error is present but the secret is redacted
        self.assertIn("ValueError", payload["error"])
        self.assertNotIn("sk-topsecret9999", payload["error"])


class ConfigureLoggingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._root = logging.getLogger()
        self._saved_handlers = self._root.handlers[:]
        self._saved_level = self._root.level

    def tearDown(self) -> None:
        self._root.handlers[:] = self._saved_handlers
        self._root.setLevel(self._saved_level)

    def test_json_format_installs_json_handler(self) -> None:
        # GIVEN VOICE_LOG_FORMAT=json
        stream = io.StringIO()
        with mock.patch.dict("os.environ", {"VOICE_LOG_FORMAT": "json"}):
            # WHEN logging is configured
            installed = configure_logging(stream=stream)
        # THEN the JSON handler is installed and emits parseable JSON with the message
        self.assertTrue(installed)
        logging.getLogger("web_voice.cfg").info("hello world")
        line = stream.getvalue().strip()
        self.assertEqual(json.loads(line)["message"], "hello world")

    def test_default_text_installs_sanitizing_handler(self) -> None:
        # GIVEN no VOICE_LOG_FORMAT (text default)
        stream = io.StringIO()
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("VOICE_LOG_FORMAT", None)
            # WHEN logging is configured
            installed = configure_logging(stream=stream)
        # THEN JSON is NOT reported, but a sanitizing text handler is installed
        self.assertFalse(installed)
        self.assertEqual(len(self._root.handlers), 1)
        self.assertIsInstance(self._root.handlers[0].formatter, SanitizingTextFormatter)

    def test_text_mode_scrubs_secret_and_path(self) -> None:
        # GIVEN text mode and a line carrying a secret token + a path
        stream = io.StringIO()
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("VOICE_LOG_FORMAT", None)
            configure_logging(stream=stream)
        logging.getLogger("web_voice.cfg").warning("auth failed key=sk-abc123def456 file /etc/voice/secret.env")
        line = stream.getvalue()
        # THEN neither the secret nor the path survive the text line
        self.assertNotIn("sk-abc123def456", line)
        self.assertNotIn("/etc/voice/secret.env", line)
        self.assertIn("<redacted-id>", line)
        self.assertIn("<redacted-path>", line)
        self.assertIn("auth", line)


class SanitizingTextFormatterTest(unittest.TestCase):
    def test_scrubs_message_and_stamps_correlation_id(self) -> None:
        # GIVEN the text formatter and a correlation id in scope
        formatter = SanitizingTextFormatter("%(levelname)s [%(correlation_id)s] %(message)s")
        with correlation_id_scope("corr-77"):
            out = formatter.format(_record("token sk-topsecret9999 here"))
        # THEN the secret is redacted and the correlation id is stamped
        self.assertNotIn("sk-topsecret9999", out)
        self.assertIn("<redacted-id>", out)
        self.assertIn("[corr-77]", out)

    def test_no_correlation_id_renders_dash(self) -> None:
        # GIVEN no correlation id in scope
        formatter = SanitizingTextFormatter("[%(correlation_id)s] %(message)s")
        out = formatter.format(_record("plain line"))
        # THEN the join-key field renders a dash, not a crash
        self.assertIn("[-]", out)

    def test_multiline_exception_stays_multiline_and_scrubbed(self) -> None:
        # GIVEN a record carrying a multi-line traceback with a secret
        formatter = SanitizingTextFormatter("%(message)s")
        try:
            raise ValueError("bad token sk-topsecret9999 at /etc/voice/x.env")
        except ValueError:
            record = _record("stream failure", level=logging.ERROR, exc_info=sys.exc_info())
        out = formatter.format(record)
        # THEN the traceback keeps multiple lines (not collapsed) and is scrubbed
        self.assertGreater(len(out.splitlines()), 1)
        self.assertIn("Traceback", out)
        self.assertNotIn("sk-topsecret9999", out)
        self.assertNotIn("/etc/voice/x.env", out)


if __name__ == "__main__":
    unittest.main()
