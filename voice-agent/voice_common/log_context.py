"""Correlation-id log context for the voice runtime (TASK-OBS-002).

A process-wide `contextvar` carrying the current connection/turn correlation id so the
structured log formatter can stamp every line without threading the id through every call
site. Async-safe: `contextvars` are copied into child tasks at creation time, so a value set
at a connection boundary (before the pipeline tasks are created) is inherited by that
connection's frame-processing tasks. It is NOT propagated into `run_in_executor` threads —
the batch REST path (thread executor) must set it inside the worker if needed (follow-up).
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar, Token
from typing import Iterator

_correlation_id: ContextVar[str | None] = ContextVar("voice_correlation_id", default=None)


def set_correlation_id(value: str | None) -> Token:
    """Bind the correlation id for the current context; returns a token for reset()."""
    return _correlation_id.set(value or None)


def get_correlation_id() -> str | None:
    """Return the correlation id in scope, or None when unset."""
    return _correlation_id.get()


def reset_correlation_id(token: Token) -> None:
    """Restore the correlation id to its value before the matching set()."""
    _correlation_id.reset(token)


@contextlib.contextmanager
def correlation_id_scope(value: str | None) -> Iterator[None]:
    """Bind the correlation id for the duration of a `with` block, then restore it."""
    token = _correlation_id.set(value or None)
    try:
        yield
    finally:
        _correlation_id.reset(token)
