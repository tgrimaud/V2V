"""Graceful active-session draining for the voice bridge (TASK-OPS-010, BUG-018 fix #3).

The bridge runs N concurrent live sessions on ONE asyncio loop: the WebSocket `/ws` path
(the primary V1 transport per ADR-0046) and the Genesys AudioHook path both count their
sessions on an `_ActiveSessions.count`. A rolling deploy / failover recreates the container;
before TASK-OPS-010 the deploy could only *stop new calls* at the load balancer
(TASK-INFRA-007) then wait a fixed grace window (`voice_drain_grace_seconds`) — it never
actually waited for the in-flight calls to end, so a still-talking caller was hard-cut on
recreate (one BUG-018 root cause).

`DrainController` closes that gap at the bridge itself. `begin_drain()` flips a flag the
transport handlers consult to refuse NEW connections (WS close 1013, exactly like the
capacity ceiling); `wait_drained()` then blocks until the registered active-session counters
sum to zero OR a bounded timeout elapses. The `POST /drain` endpoint (`web_voice/app.py`)
drives it so the Ansible voice deploy can wait for "0 active calls" before recreate,
degrading to the existing grace behaviour on timeout / failure — draining is a safety
improvement, never a deploy gate (fail-safe).

This is the SESSION-level drain (whole call), distinct from the per-turn TTS `drain()`
(TASK-WEB-008 / ADR-0025) that finalizes a trailing utterance inside one live session.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

# Env knobs (rendered by the Ansible voice deploy). The token gates the control endpoint;
# an unset token disables `POST /drain` (fail-closed), so the routed :8090 never exposes an
# unauthenticated "stop taking calls" trigger at the HAProxy edge.
DRAIN_TOKEN_ENV_VAR = "VOICE_DRAIN_TOKEN"
DRAIN_TIMEOUT_ENV_VAR = "VOICE_DRAIN_TIMEOUT_MS"
DEFAULT_DRAIN_TIMEOUT_MS = 90_000
# Poll cadence while waiting for in-flight calls to end: small enough to return promptly
# once the last caller hangs up, large enough not to busy-spin the shared asyncio loop.
_POLL_INTERVAL_S = 0.25

# Telemetry names (US-036 style): the deploy + a pilot chart can see drain outcomes per host.
DRAIN_REQUESTED_EVENT = "voice.drain.requested"
DRAIN_COMPLETED_EVENT = "voice.drain.completed"
DRAIN_REMAINING_METRIC = "voice.drain.remaining_sessions"


@dataclass(frozen=True)
class DrainOutcome:
    """Result of one bounded drain wait."""

    drained: bool          # True = 0 active sessions reached within the timeout
    started_active: int    # active sessions when the drain began
    remaining: int         # active sessions still running when the wait returned
    elapsed_ms: float
    timed_out: bool

    @property
    def status(self) -> str:
        return "drained" if self.drained else "timeout"


class DrainController:
    """Coordinate a graceful session-level drain across the bridge's live transports.

    Each transport registers a zero-arg counter returning its current active-session count
    (WS + Genesys both expose `_ActiveSessions.count`). The controller sums them and never
    reaches into transport internals, so a new transport only has to register its counter.
    One asyncio loop means no lock is needed: a handler never preempts between the drain-flag
    read and the counter read.
    """

    def __init__(
        self, token: str | None = None, default_timeout_ms: int = DEFAULT_DRAIN_TIMEOUT_MS
    ) -> None:
        self._token = token or None
        self._default_timeout_ms = max(0, default_timeout_ms)
        self._draining = False
        self._counters: list[Callable[[], int]] = []

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def default_timeout_ms(self) -> int:
        return self._default_timeout_ms

    def register_counter(self, counter: Callable[[], int]) -> None:
        """Register a transport's active-session counter (summed by `active_sessions`)."""
        self._counters.append(counter)

    def is_draining(self) -> bool:
        return self._draining

    def active_sessions(self) -> int:
        return sum(max(0, int(counter())) for counter in self._counters)

    def begin_drain(self) -> None:
        """Stop accepting new sessions (transport handlers refuse with WS 1013)."""
        self._draining = True

    def resume(self) -> None:
        """Re-open the bridge to new sessions (fail-safe abort of a drain)."""
        self._draining = False

    async def wait_drained(
        self,
        timeout_ms: int | None = None,
        *,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> DrainOutcome:
        """Flip to draining, then wait until 0 active sessions or the timeout elapses.

        Safe to call repeatedly. `sleep`/`monotonic` are injectable so tests drive time
        deterministically without real waits.
        """
        self.begin_drain()
        budget_ms = self._default_timeout_ms if timeout_ms is None else max(0, timeout_ms)
        start = monotonic()
        deadline = start + budget_ms / 1000.0
        started = self.active_sessions()
        remaining = started
        while remaining > 0:
            now = monotonic()
            if now >= deadline:
                return DrainOutcome(False, started, remaining, (now - start) * 1000.0, True)
            await sleep(min(_POLL_INTERVAL_S, max(0.0, deadline - now)))
            remaining = self.active_sessions()
        return DrainOutcome(True, started, 0, (monotonic() - start) * 1000.0, False)


def drain_token_config() -> str | None:
    """Control-endpoint token from the environment (None/empty = `POST /drain` disabled)."""
    raw = os.environ.get(DRAIN_TOKEN_ENV_VAR)
    return raw.strip() if raw and raw.strip() else None


def drain_timeout_ms_config() -> int:
    """Default drain wait budget in ms (non-numeric / non-positive falls back to the default)."""
    raw = os.environ.get(DRAIN_TIMEOUT_ENV_VAR)
    if raw is None:
        return DEFAULT_DRAIN_TIMEOUT_MS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_DRAIN_TIMEOUT_MS
    return value if value > 0 else DEFAULT_DRAIN_TIMEOUT_MS
