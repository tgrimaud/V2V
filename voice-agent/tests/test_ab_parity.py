"""Regression test for the A/B parity harness (TASK-WEB-005, ST-8)."""

import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))
sys.path.insert(0, str(VOICE_AGENT_ROOT / "scripts"))

from ab_parity import run_ab_parity  # noqa: E402


class AbParityHarnessTest(unittest.TestCase):
    def test_stdlib_and_pipecat_produce_identical_output(self) -> None:
        # GIVEN the A/B harness over a few turns
        report = run_ab_parity(iterations=3)
        # THEN every turn is byte-identical across runtimes
        self.assertTrue(report.all_identical)
        self.assertEqual(report.mismatches, 0)
        self.assertEqual(report.iterations, 3)

    def test_summary_reports_latency_for_both_runtimes(self) -> None:
        # GIVEN a harness run
        summary = run_ab_parity(iterations=2).summary()
        # THEN both runtimes carry a latency distribution
        self.assertEqual(summary["stdlib"]["count"], 2)
        self.assertEqual(summary["pipecat"]["count"], 2)
        self.assertIn("mean_ms", summary["pipecat"])


if __name__ == "__main__":
    unittest.main()
