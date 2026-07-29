"""Keeps one streaming provider session pre-opened, off the per-turn critical path.

Provider-agnostic warm-up helper shared by the STT and TTS streaming processors
(TASK-WEB-011 TTS pre-warm, TASK-WEB-021 STT pre-warm / lever 2). Gradium's STT and
TTS WebSockets are single-use — a session cannot be *reused* across turns, but it can
be *pre-warmed*: `start()` kicks off the open in the background, `acquire()` hands out
the ready spare (or opens on demand if none/failed), and `aclose()` discards an unused
spare at call end so a pre-warmed connection is never leaked.

It never invents audio or a transcript and carries no secret (the provider owns the
key). A failed or absent spare never blocks the turn — `acquire()` falls back to a
fresh on-demand open whose failure propagates so the caller reports it (never silently).
"""

import asyncio
from typing import Any

# Outcome of the last acquire(), exposed for observability (TASK-WEB-021): the caller can
# emit it so QA can tell a pre-warm hit from a fallback without guessing from slice timing.
ACQUIRE_HIT = "hit"  # the pre-opened spare was used (connect+setup was off the turn path)
ACQUIRE_FALLBACK = "fallback"  # the spare's open failed -> a fresh on-demand open was used
ACQUIRE_COLD = "cold"  # no spare was pre-opened (start() not called) -> on-demand open


class SessionWarmer:
    """Keeps one streaming provider session pre-opened, off the per-turn critical path."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self._task: "asyncio.Future[Any] | None" = None
        # Set by acquire() to ACQUIRE_HIT / ACQUIRE_FALLBACK / ACQUIRE_COLD for observability;
        # None until the first acquire(). A consumer that ignores it (TTS) is unaffected.
        self.last_acquire: str | None = None

    def start(self) -> None:
        """Begin opening a spare session in the background (idempotent)."""
        if self._task is None:
            self._task = asyncio.ensure_future(self._provider.open())

    async def acquire(self) -> Any:
        """Return a ready session: the pre-opened spare if its open succeeded, else a
        fresh on-demand open. A failed or absent spare never blocks the turn; an
        on-demand open failure propagates so the caller reports it (never a silent turn).
        Records the outcome in `last_acquire` for the caller to surface as telemetry.
        """
        task, self._task = self._task, None
        if task is not None:
            try:
                session = await task
                self.last_acquire = ACQUIRE_HIT
                return session
            except Exception:
                self.last_acquire = ACQUIRE_FALLBACK  # spare open failed -> fresh open
                return await self._provider.open()
        self.last_acquire = ACQUIRE_COLD
        return await self._provider.open()

    async def aclose(self) -> None:
        """Discard any spare (call end): cancel the pending open, or close the socket
        if it already opened, so a pre-warmed connection is never leaked."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            session = await task
        except asyncio.CancelledError:
            # The spare task's own cancellation (what we just requested) is expected and
            # must be swallowed. But if OUR coroutine is being cancelled externally, the
            # CancelledError must propagate — swallowing it would suppress the outer cancel
            # (repo rule: never absorb an external CancelledError).
            current = asyncio.current_task()
            if current is not None and current.cancelling() > 0:
                raise
            return
        except Exception:
            return  # the spare open failed -> nothing to close
        try:
            await session.aclose()
        except Exception:
            pass  # best-effort close of an unused spare
