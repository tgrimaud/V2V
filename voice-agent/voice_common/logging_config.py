"""Structured JSON logging for the voice runtime (TASK-OBS-002).

Off by default (human-readable text) so local dev and tests are unchanged; setting
`VOICE_LOG_FORMAT=json` makes the root logger emit ONE sanitized JSON object per line, each
stamped with the correlation id in scope (`log_context`) when there is one. This mirrors the
backend's Spring-native structured logging (`LOGGING_STRUCTURED_FORMAT_CONSOLE=ecs`) so SRE
ingests one shape across both tiers, and it never blocks a call — logging is best-effort.

The message and any exception text are passed through `sanitize.scrub_message` so a log line
can never leak a path, filename, UUID, secret-prefixed token or long opaque/numeric id.
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


def configure_logging(stream: TextIO | None = None, *, level: int = logging.INFO) -> bool:
    """Install the structured JSON handler on the root logger when enabled.

    Returns True when JSON logging was installed (`VOICE_LOG_FORMAT=json`), False otherwise
    (the default text logging is left untouched). Idempotent: replaces the root handlers so a
    repeated call does not stack duplicate handlers. Called once at server startup.
    """
    fmt = os.environ.get(_ENV_VAR, "").strip().lower()
    if fmt != JSON_FORMAT:
        return False  # default: leave text logging (handlers + level) untouched
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    return True
