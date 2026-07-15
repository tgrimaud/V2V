"""Background asyncio event loop for the streaming voice runtime
(Sprint 6 / TASK-WEB-007).

The web server is a threaded stdlib `http.server` (synchronous request handlers),
but the WebRTC transport + Pipecat pipeline need a **single, persistent** asyncio
loop that outlives individual requests: the signaling POST returns immediately while
the media session keeps running on that loop (single long-lived loop, RF-012).

`BackgroundEventLoop` runs one loop in a daemon thread. Synchronous request handlers
submit coroutines with `run(coro)` (blocking, for the offer→answer round trip) or
`spawn(coro)` (fire-and-forget, for the long-lived session task). All WebRTC
connections, transports and pipelines live on this one loop, so nothing crosses
threads except the coroutine submission itself.
"""

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Coroutine


class BackgroundEventLoop:
    """Owns one asyncio loop on a daemon thread; submit coroutines thread-safely."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_forever, name="voice-webrtc-loop", daemon=True
        )
        self._started = threading.Event()

    def start(self) -> None:
        if self._thread.is_alive():
            return
        self._thread.start()
        self._started.wait(timeout=5)

    def _run_forever(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._started.set)
        self._loop.run_forever()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    def run(self, coro: Coroutine[Any, Any, Any], *, timeout: float | None = None) -> Any:
        """Submit a coroutine and block until it returns (for request/response)."""
        future: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> Future:
        """Submit a fire-and-forget coroutine (e.g. the long-lived session task)."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self) -> None:
        """Cancel pending tasks, stop the loop and join the thread (graceful shutdown)."""
        if not self._thread.is_alive():
            return
        try:
            asyncio.run_coroutine_threadsafe(self._cancel_all(), self._loop).result(timeout=5)
        except Exception:  # noqa: BLE001 - best-effort drain; we stop the loop regardless
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    async def _cancel_all(self) -> None:
        pending = [t for t in asyncio.all_tasks(self._loop) if t is not asyncio.current_task()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
