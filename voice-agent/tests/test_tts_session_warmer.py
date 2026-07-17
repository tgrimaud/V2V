"""Tests for the TTS session pre-warmer (TASK-WEB-011).

`TtsSessionWarmer` keeps one streaming TTS session pre-opened so the connect+setup
handshake is off the per-turn critical path. These tests prove, with a fake provider
(no network), that it:
- hands out the pre-opened spare without a second open (`start` -> `acquire`);
- opens on demand when no spare was started;
- is idempotent on repeated `start`;
- falls back to a fresh open when the spare's open failed (never blocks a turn);
- propagates an on-demand open failure (never a silent dead turn);
- closes an unused opened spare and cancels a still-pending spare open (no leak).
"""

import asyncio
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from web_voice.tts_session_warmer import TtsSessionWarmer  # noqa: E402


class WarmSession:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class WarmProvider:
    """Fake streaming TTS provider: records opens, can fail selected opens or block."""

    name = "fake-streaming-tts"

    def __init__(self, *, fail_opens=None, block=None) -> None:
        self.open_count = 0
        self._fail_opens = set(fail_opens or ())
        self._block = block
        self.sessions: list[WarmSession] = []

    async def open(self) -> WarmSession:
        self.open_count += 1
        index = self.open_count
        if self._block is not None:
            await self._block.wait()
        if index in self._fail_opens:
            raise RuntimeError("connect failed")
        session = WarmSession(f"s{index}")
        self.sessions.append(session)
        return session


class TtsSessionWarmerTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_then_acquire_returns_preopened_spare_without_second_open(self):
        # GIVEN a spare pre-opened via start()
        provider = WarmProvider()
        warmer = TtsSessionWarmer(provider)
        warmer.start()
        # WHEN the turn acquires a session
        session = await warmer.acquire()
        # THEN it is the pre-opened spare, opened exactly once (connect off the turn path)
        self.assertEqual(provider.open_count, 1)
        self.assertIs(session, provider.sessions[0])

    async def test_acquire_without_start_opens_on_demand(self):
        # GIVEN no spare was started
        provider = WarmProvider()
        warmer = TtsSessionWarmer(provider)
        # WHEN a turn acquires
        session = await warmer.acquire()
        # THEN it opens on demand (fallback), still exactly one open
        self.assertEqual(provider.open_count, 1)
        self.assertIs(session, provider.sessions[0])

    async def test_start_is_idempotent(self):
        # GIVEN start() called twice before any acquire
        provider = WarmProvider()
        warmer = TtsSessionWarmer(provider)
        warmer.start()
        warmer.start()
        # WHEN the turn acquires
        await warmer.acquire()
        # THEN only one spare was opened
        self.assertEqual(provider.open_count, 1)

    async def test_acquire_falls_back_when_spare_open_failed(self):
        # GIVEN the pre-opened spare's open fails (auth/credit/drop at handshake)
        provider = WarmProvider(fail_opens={1})
        warmer = TtsSessionWarmer(provider)
        warmer.start()
        # WHEN the turn acquires
        session = await warmer.acquire()
        # THEN it does NOT raise: it falls back to a fresh on-demand open
        self.assertIsNotNone(session)
        self.assertEqual(provider.open_count, 2)

    async def test_acquire_propagates_on_demand_open_failure(self):
        # GIVEN no spare and the on-demand open fails
        provider = WarmProvider(fail_opens={1})
        warmer = TtsSessionWarmer(provider)
        # WHEN a turn acquires with no spare available
        # THEN the failure propagates so the caller reports it (never a silent turn)
        with self.assertRaises(RuntimeError):
            await warmer.acquire()

    async def test_aclose_closes_unused_opened_spare(self):
        # GIVEN a spare opened but never acquired (call ended)
        provider = WarmProvider()
        warmer = TtsSessionWarmer(provider)
        warmer.start()
        await asyncio.sleep(0)  # let the spare finish opening
        # WHEN the warmer is closed
        await warmer.aclose()
        # THEN the unused spare's socket is closed (not leaked)
        self.assertTrue(provider.sessions[0].closed)

    async def test_aclose_cancels_pending_spare_open(self):
        # GIVEN a spare whose open is still in flight (blocked)
        gate = asyncio.Event()
        provider = WarmProvider(block=gate)
        warmer = TtsSessionWarmer(provider)
        warmer.start()
        await asyncio.sleep(0)  # the open task started and is blocked on the gate
        # WHEN the warmer is closed before the open completes
        await warmer.aclose()
        gate.set()
        await asyncio.sleep(0)
        # THEN the pending open is cancelled — no session is ever created/leaked
        self.assertEqual(provider.sessions, [])

    async def test_aclose_without_spare_is_noop(self):
        # GIVEN no spare was started
        provider = WarmProvider()
        warmer = TtsSessionWarmer(provider)
        # WHEN closed
        await warmer.aclose()
        # THEN nothing was opened and no error is raised
        self.assertEqual(provider.open_count, 0)


if __name__ == "__main__":
    unittest.main()
