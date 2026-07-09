import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stt_validation.telemetry import LatencyReport  # noqa: E402


class LatencyReportTest(unittest.TestCase):
    def test_empty_sample_set_yields_zero_count_and_no_percentiles(self) -> None:
        # GIVEN / WHEN
        report = LatencyReport.from_samples([])

        # THEN
        self.assertEqual(report.count, 0)
        self.assertIsNone(report.p50_ms)
        self.assertIsNone(report.p95_ms)
        self.assertIsNone(report.p99_ms)

    def test_percentiles_use_nearest_rank_over_sorted_samples(self) -> None:
        # GIVEN
        samples = [float(value) for value in range(1, 101)]

        # WHEN
        report = LatencyReport.from_samples(samples)

        # THEN
        self.assertEqual(report.count, 100)
        self.assertEqual(report.min_ms, 1.0)
        self.assertEqual(report.max_ms, 100.0)
        self.assertEqual(report.p50_ms, 50.0)
        self.assertEqual(report.p95_ms, 95.0)
        self.assertEqual(report.p99_ms, 99.0)

    def test_single_sample_contributes_to_every_percentile(self) -> None:
        # GIVEN / WHEN
        report = LatencyReport.from_samples([42.0])

        # THEN
        self.assertEqual(report.count, 1)
        self.assertEqual(report.p50_ms, 42.0)
        self.assertEqual(report.p95_ms, 42.0)
        self.assertEqual(report.p99_ms, 42.0)


if __name__ == "__main__":
    unittest.main()
