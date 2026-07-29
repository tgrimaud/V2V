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


class SessionWarmer:
    """Keeps one streaming provider session pre-opened, off the per-turn critical path."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self._task: "asyncio.Future[Any] | None" = None

    def start(self) -> None:
        """Begin opening a spare session in the background (idempotent)."""
        if self._task is None:
            self._task = asyncio.ensure_future(self._provider.open())

    async def acquire(self) -> Any:
        """Return a ready session: the pre-opened spare if its open succeeded, else a
        fresh on-demand open. A failed or absent spare never blocks the turn; an
        on-demand open failure propagates so the caller reports it (never a silent turn).
        """
        task, self._task = self._task, None
        if task is not None:
            try:
                return await task
            except Exception:
                pass  # spare open failed -> fall back to a fresh on-demand open
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
        except BaseException:
            return  # cancelled before it opened, or the open failed -> nothing to close
        try:
            await session.aclose()
        except Exception:
            pass  # best-effort close of an unused spare
