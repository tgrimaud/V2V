import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stt_validation import (  # noqa: E402
    FixtureSttProvider,
    SttValidationRunner,
    TelemetryRecorder,
    evaluate_fixture_set,
)
from stt_validation.manifest import load_manifest  # noqa: E402

MANIFEST = Path(__file__).resolve().parents[1] / "fixtures" / "manifest.json"


class ManifestTest(unittest.TestCase):
    def test_committed_manifest_covers_all_declared_categories(self) -> None:
        # GIVEN
        manifest = load_manifest(MANIFEST)

        # WHEN
        report = evaluate_fixture_set(
            SttValidationRunner(FixtureSttProvider(), TelemetryRecorder()),
            manifest.specs,
            manifest.expected_categories,
            manifest.quality_threshold,
        )

        # THEN
        self.assertEqual(report.missing_categories, [])
        self.assertEqual(report.failed_categories(), [])
        self.assertTrue(report.ready)
        self.assertEqual(report.latency.count, 22)

    def test_committed_manifest_has_multiple_samples_per_usable_category(self) -> None:
        # GIVEN
        manifest = load_manifest(MANIFEST)

        # WHEN
        report = evaluate_fixture_set(
            SttValidationRunner(FixtureSttProvider(), TelemetryRecorder()),
            manifest.specs,
            manifest.expected_categories,
            manifest.quality_threshold,
        )

        # THEN each usable category has 5 samples (statistically reportable),
        # silence has 2 and is flagged as not yet significant.
        counts = {c.category: c.sample_count for c in report.category_summaries}
        self.assertEqual(counts, {"short": 5, "long": 5, "noisy": 5, "accented": 5, "silence": 2})
        self.assertEqual(report.underpowered_categories(), ["silence"])


if __name__ == "__main__":
    unittest.main()
