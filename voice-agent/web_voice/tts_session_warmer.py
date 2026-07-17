"""Pre-opens a streaming TTS session so the connect + setup handshake is off the
per-turn critical path (TASK-WEB-011).

Gradium's TTS WebSocket is single-use: after one `synthesize()` + `end_of_stream`
the socket closes (a second synthesize on the same connection fails), so the
connection cannot be *reused* across turns — but it can be *pre-warmed*. This helper
keeps at most one spare session opening/opened in the background: `start()` kicks off
the open, `acquire()` hands out the ready spare (or opens on demand if none/failed),
and `aclose()` discards an unused spare at call end.

Measured impact (TASK-STT-013 post-fix baseline, docs/qa/stt-013-finalize-tail-spike.md):
the TTS `open()` costs ~90 ms warm / ~188 ms cold; moving it off the per-turn path
brings `tts_first_audio` p95 ~484 -> ~394 ms and the composite under the ADR-0018
800 ms gate. It never invents audio and carries no secret (the provider owns the key).
"""

import asyncio
from typing import Any


class TtsSessionWarmer:
    """Keeps one streaming TTS session pre-opened, off the per-turn critical path."""

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
