"""Structured logging for the voice runtime (TASK-OBS-002, hardened TASK-OPS-015 V1b).

`VOICE_LOG_FORMAT=json` makes the root logger emit ONE sanitized JSON object per line, each
stamped with the correlation id in scope (`log_context`) when there is one. This mirrors the
backend's Spring-native structured logging (`LOGGING_STRUCTURED_FORMAT_CONSOLE=ecs`) so SRE
ingests one shape across both tiers, and it never blocks a call — logging is best-effort.

The text default (any other value) stays human-readable but is **also sanitized** since
TASK-OPS-015 V1b: both formatters pass the message AND any exception / stack text through
`sanitize.scrub_message`, so a log line can never leak a path, filename, UUID, secret-prefixed
token or long opaque/numeric id — in text mode too, not just JSON. The text formatter scrubs
exception/stack text line by line so multi-line tracebacks stay readable.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, TextIO

from .log_context import get_correlation_id
from .sanitization import scrub_message

JSON_FORMAT = "json"
_ENV_VAR = "VOICE_LOG_FORMAT"
# Human-readable text layout for the non-JSON default. `[%(correlation_id)s]` gives text mode
# the same join key the JSON shape carries (SanitizingTextFormatter fills it from log_context).
_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(correlation_id)s] %(message)s"


class JsonLogFormatter(logging.Formatter):
    """Render a `LogRecord` as one sanitized JSON object.

    Fixed keys (`timestamp`, `level`, `logger`, `message`, optional `correlation_id` and
    `error`) keep the shape stable for ingestion. Only these keys are emitted — arbitrary
    record attributes are not dumped, so an accidental `extra=` never leaks unsanitized data.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub_message(record.getMessage()),
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id
        if record.exc_info:
            exc_type = record.exc_info[0]
            exc_value = record.exc_info[1]
            payload["error"] = scrub_message(
                f"{exc_type.__name__}: {exc_value}" if exc_type else str(exc_value)
            )
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class SanitizingTextFormatter(logging.Formatter):
    """Human-readable text formatter that scrubs the message, exception and stack text.

    The text default's counterpart to `JsonLogFormatter` (TASK-OPS-015 V1b): it keeps the
    familiar one-line layout but runs the same `scrub_message` redaction so text mode can
    never leak a path, filename, UUID, secret-prefixed token or long opaque id. The message
    is scrubbed via `formatMessage`; exception and stack text are scrubbed **line by line**
    (`formatException`/`formatStack`) so a multi-line traceback stays multi-line. The
    correlation id in scope is exposed as a record attribute for `_TEXT_FORMAT`.
    """

    def format(self, record: logging.LogRecord) -> str:
        record.correlation_id = get_correlation_id() or "-"
        return super().format(record)

    def formatMessage(self, record: logging.LogRecord) -> str:
        record.message = scrub_message(record.message)
        return super().formatMessage(record)

    def formatException(self, ei: Any) -> str:
        return self._scrub_lines(super().formatException(ei))

    def formatStack(self, stack_info: str) -> str:
        return self._scrub_lines(super().formatStack(stack_info))

    @staticmethod
    def _scrub_lines(text: str) -> str:
        return "\n".join(scrub_message(line) for line in text.splitlines())


def configure_logging(stream: TextIO | None = None, *, level: int = logging.INFO) -> bool:
    """Install the root logging handler, sanitized in both JSON and text modes.

    `VOICE_LOG_FORMAT=json` installs the structured `JsonLogFormatter`; any other value
    installs the human-readable `SanitizingTextFormatter` — both scrub the message and any
    exception/stack text, so text mode is safe by default too (TASK-OPS-015 V1b), not only
    JSON. Returns True when JSON logging was installed, False for the text default.
    Idempotent: replaces the root handlers so a repeated call does not stack duplicates.
    Called once at server startup.
    """
    json_mode = os.environ.get(_ENV_VAR, "").strip().lower() == JSON_FORMAT
    formatter: logging.Formatter = JsonLogFormatter() if json_mode else SanitizingTextFormatter(_TEXT_FORMAT)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    return json_mode
