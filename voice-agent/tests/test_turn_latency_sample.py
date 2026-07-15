"""Tests for the full-turn per-slice latency sample (TASK-WEB-003-G / US-036)."""

import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))
sys.path.insert(0, str(VOICE_AGENT_ROOT / "scripts"))

from turn_latency_sample import run_sample  # noqa: E402
from voice_common.pipeline_timing import PIPELINE_SLICES  # noqa: E402


class TurnLatencySampleTest(unittest.TestCase):
    def _measured(self, result) -> set[str]:
        return {s["slice"] for s in result["report"]["slices"] if s["measured"]}

    def test_success_run_measures_every_canonical_slice(self) -> None:
        # GIVEN a normal (stub backend) full-turn sample on the stdlib runtime
        result = run_sample(iterations=5, runtime="stdlib", degraded=False)
        # THEN all six US-036 slices are measured (no gap masquerading as fast)
        self.assertEqual(self._measured(result), set(PIPELINE_SLICES))
        self.assertEqual(result["backend"], "stub-backend")

    def test_degraded_run_still_measures_the_backend_and_tts_slices(self) -> None:
        # GIVEN a degraded (unavailable backend) full-turn sample
        result = run_sample(iterations=5, runtime="stdlib", degraded=True)
        # THEN the safe fallback is still spoken, so backend + tts + egress stay measured
        measured = self._measured(result)
        self.assertEqual(measured, set(PIPELINE_SLICES))
        self.assertTrue(result["degraded"])

    def test_pipecat_runtime_measures_every_slice_too(self) -> None:
        # GIVEN the pipecat runtime
        result = run_sample(iterations=3, runtime="pipecat", degraded=False)
        # THEN it measures the same slices (runtime-agnostic report)
        self.assertEqual(self._measured(result), set(PIPELINE_SLICES))


if __name__ == "__main__":
    unittest.main()
