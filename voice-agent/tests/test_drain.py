"""Unit tests for the graceful session-drain controller (TASK-OPS-010, BUG-018 fix #3).

Covers `DrainController` (draining flag, registered active-session counters, the bounded
`wait_drained` loop with injected clock/sleep so no real time passes) and the env config
helpers `drain_token_config` / `drain_timeout_ms_config`.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web_voice.drain import (  # noqa: E402
    DEFAULT_DRAIN_TIMEOUT_MS,
    DrainController,
    DrainOutcome,
    drain_timeout_ms_config,
    drain_token_config,
)


class _Clock:
    """Fake monotonic clock advanced only by the injected `sleep` (no real waiting)."""

    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    async def sleep(self, dt: float) -> None:
        self.t += dt


class _Counter:
    """Active-session counter returning successive scripted values (last value sticks)."""

    def __init__(self, values) -> None:  # noqa: ANN001
        self.values = list(values)
        self.i = 0

    def __call__(self) -> int:
        value = self.values[min(self.i, len(self.values) - 1)]
        self.i += 1
        return value


class DrainControllerStateTest(unittest.TestCase):
    def test_starts_not_draining_and_flips_on_begin(self) -> None:
        controller = DrainController()
        self.assertFalse(controller.is_draining())
        controller.begin_drain()
        self.assertTrue(controller.is_draining())

    def test_resume_reopens_after_drain(self) -> None:
        controller = DrainController()
        controller.begin_drain()
        controller.resume()
        self.assertFalse(controller.is_draining())

    def test_active_sessions_sums_registered_counters_and_clamps_negatives(self) -> None:
        controller = DrainController()
        controller.register_counter(lambda: 3)
        controller.register_counter(lambda: 2)
        controller.register_counter(lambda: -5)  # a racy transient must not go negative
        self.assertEqual(controller.active_sessions(), 5)

    def test_no_counters_reports_zero_active(self) -> None:
        self.assertEqual(DrainController().active_sessions(), 0)


class DrainOutcomeTest(unittest.TestCase):
    def test_status_maps_drained_and_timeout(self) -> None:
        self.assertEqual(DrainOutcome(True, 2, 0, 1.0, False).status, "drained")
        self.assertEqual(DrainOutcome(False, 2, 2, 9.0, True).status, "timeout")


class WaitDrainedTest(unittest.IsolatedAsyncioTestCase):
    async def test_zero_active_returns_drained_immediately(self) -> None:
        clock = _Clock()
        controller = DrainController()
        controller.register_counter(lambda: 0)
        outcome = await controller.wait_drained(5000, sleep=clock.sleep, monotonic=clock.now)
        self.assertTrue(outcome.drained)
        self.assertEqual(outcome.remaining, 0)
        self.assertEqual(outcome.started_active, 0)
        self.assertEqual(clock.now(), 0.0)  # never slept
        # wait_drained also flips the flag so new sessions are refused during the wait.
        self.assertTrue(controller.is_draining())

    async def test_waits_until_zero_then_reports_drained(self) -> None:
        clock = _Clock()
        controller = DrainController()
        controller.register_counter(_Counter([2, 2, 1, 0]))
        outcome = await controller.wait_drained(10_000, sleep=clock.sleep, monotonic=clock.now)
        self.assertTrue(outcome.drained)
        self.assertEqual(outcome.started_active, 2)
        self.assertEqual(outcome.remaining, 0)
        self.assertFalse(outcome.timed_out)

    async def test_times_out_when_calls_never_end(self) -> None:
        clock = _Clock()
        controller = DrainController()
        controller.register_counter(lambda: 2)  # stuck call, never drains
        outcome = await controller.wait_drained(100, sleep=clock.sleep, monotonic=clock.now)
        self.assertFalse(outcome.drained)
        self.assertTrue(outcome.timed_out)
        self.assertEqual(outcome.status, "timeout")
        self.assertEqual(outcome.remaining, 2)
        self.assertEqual(outcome.started_active, 2)

    async def test_zero_budget_with_active_calls_times_out_without_sleeping(self) -> None:
        clock = _Clock()
        controller = DrainController()
        controller.register_counter(lambda: 1)
        outcome = await controller.wait_drained(0, sleep=clock.sleep, monotonic=clock.now)
        self.assertFalse(outcome.drained)
        self.assertEqual(clock.now(), 0.0)


class DrainConfigTest(unittest.TestCase):
    def test_token_none_when_unset_or_blank(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(drain_token_config())
        with mock.patch.dict("os.environ", {"VOICE_DRAIN_TOKEN": "   "}, clear=True):
            self.assertIsNone(drain_token_config())

    def test_token_trimmed_when_set(self) -> None:
        with mock.patch.dict("os.environ", {"VOICE_DRAIN_TOKEN": "  s3cr3t "}, clear=True):
            self.assertEqual(drain_token_config(), "s3cr3t")

    def test_timeout_defaults_on_unset_garbage_or_non_positive(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(drain_timeout_ms_config(), DEFAULT_DRAIN_TIMEOUT_MS)
        with mock.patch.dict("os.environ", {"VOICE_DRAIN_TIMEOUT_MS": "abc"}, clear=True):
            self.assertEqual(drain_timeout_ms_config(), DEFAULT_DRAIN_TIMEOUT_MS)
        with mock.patch.dict("os.environ", {"VOICE_DRAIN_TIMEOUT_MS": "0"}, clear=True):
            self.assertEqual(drain_timeout_ms_config(), DEFAULT_DRAIN_TIMEOUT_MS)

    def test_timeout_parsed_when_positive(self) -> None:
        with mock.patch.dict("os.environ", {"VOICE_DRAIN_TIMEOUT_MS": "45000"}, clear=True):
            self.assertEqual(drain_timeout_ms_config(), 45000)


if __name__ == "__main__":
    unittest.main()
