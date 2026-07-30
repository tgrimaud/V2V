"""Streamed conversation contract (TASK-WEB-020 / lever 1, ADR-0037).

The blocking `BackendAnswerPort.answer` waits for the *whole* answer before the TTS
can start. Lever 1 consumes the backend's guarded SSE endpoint
(`POST /api/conversation/converse-stream`, ADR-0013) whose `chunk` events are emitted
**one guardrail-vetted sentence at a time** (`GuardedSentenceEmitter`: grounding +
per-sentence output guardrail before each emit, safe hand-off as a terminal chunk on a
block). Speaking each `chunk` as it arrives starts first audio on the first sentence
without weakening DEC-002 — the safety gate stays on the backend.

This module stays neutral: it imports only stdlib. The `AnswerStreamEvent` is the
parsed SSE event; `parse_sse_events` turns a raw SSE line stream into events;
`StreamControl` lets the async consumer abort an in-flight blocking read on barge-in.
"""

import json
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Callable, Protocol

from .models import AnswerRequest

# SSE event names emitted by ConverseStreamSession (backend). `chunk` = one vetted
# sentence; `done` = terminal {text, confidence?, grounded}; `error` = ErrorResponse.
CHUNK = "chunk"
DONE = "done"
ERROR = "error"


@dataclass(frozen=True)
class AnswerStreamEvent:
    """One parsed SSE event from the guarded stream.

    `text` carries a vetted sentence (`chunk`) or the full voiced answer (`done`).
    `confidence`/`grounded` are only present on `done`; `error_code`/`error_reason`
    only on `error`. Never carries the API key or a raw provider string.
    """

    kind: str
    text: str | None = None
    confidence: float | None = None
    grounded: bool | None = None
    error_code: str | None = None
    error_reason: str | None = None


class StreamControl:
    """Cooperative abort for a blocking SSE read (barge-in).

    The consumer runs the blocking generator on a worker thread; on an interruption it
    calls `abort()`, which sets the stop flag and closes the underlying response so a
    read blocked mid-line unblocks instead of waiting for the next byte. Best-effort:
    closing may race the read, which is fine — no further event is consumed once
    stopped.
    """

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._closer: Callable[[], None] | None = None

    def bind(self, closer: Callable[[], None]) -> None:
        self._closer = closer

    def abort(self) -> None:
        self._stop.set()
        closer, self._closer = self._closer, None
        if closer is not None:
            try:
                closer()
            except Exception:  # noqa: BLE001 - best-effort close; never raise on abort
                pass

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()


class StreamingBackendAnswerPort(Protocol):
    """A `BackendAnswerPort` that can also stream vetted sentences (lever 1)."""

    @property
    def name(self) -> str: ...

    def answer_stream(
        self, request: AnswerRequest, control: StreamControl | None = None
    ) -> Iterator[AnswerStreamEvent]: ...


def parse_sse_events(lines: Iterable[str]) -> Iterator[AnswerStreamEvent]:
    """Parse a raw SSE line stream into `AnswerStreamEvent`s.

    Follows the SSE framing the Spring `SseEmitter` produces: `event:<name>` +
    `data:<json>` lines, a blank line dispatches the event. Multiple `data:` lines are
    joined with a newline (SSE spec). Comment lines (`:` prefix) and unknown fields are
    ignored. A malformed data payload is skipped rather than crashing the turn.
    """
    event_name: str | None = None
    data_lines: list[str] = []
    for raw in lines:
        line = raw.rstrip("\n").rstrip("\r")
        if line == "":
            yield from _dispatch(event_name, data_lines)
            event_name, data_lines = None, []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)
    yield from _dispatch(event_name, data_lines)


def _dispatch(event_name: str | None, data_lines: list[str]) -> Iterator[AnswerStreamEvent]:
    if event_name is None or not data_lines:
        return
    payload = _load_json("\n".join(data_lines))
    if payload is None:
        return
    if event_name == CHUNK:
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            yield AnswerStreamEvent(kind=CHUNK, text=text)
    elif event_name == DONE:
        yield AnswerStreamEvent(
            kind=DONE,
            text=payload.get("text") if isinstance(payload.get("text"), str) else None,
            confidence=_as_float(payload.get("confidence")),
            grounded=payload.get("grounded") if isinstance(payload.get("grounded"), bool) else None,
        )
    elif event_name == ERROR:
        yield AnswerStreamEvent(
            kind=ERROR,
            error_code=payload.get("code") if isinstance(payload.get("code"), str) else None,
            error_reason=payload.get("message") if isinstance(payload.get("message"), str) else None,
        )


def _load_json(text: str) -> dict | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _as_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
