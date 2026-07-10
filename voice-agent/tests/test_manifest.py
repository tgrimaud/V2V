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

        # THEN each usable category has 5 samples (statistically reportable);
        # silence has 2 but is unusable, so it is excluded from the significance
        # gate rather than reported as underpowered (RF-011).
        counts = {c.category: c.sample_count for c in report.category_summaries}
        self.assertEqual(counts, {"short": 5, "long": 5, "noisy": 5, "accented": 5, "silence": 2})
        self.assertEqual(report.underpowered_categories(), [])
        self.assertTrue(report.all_categories_significant)

    def test_manifest_reference_matches_sidecar_transcript(self) -> None:
        # GIVEN the two sources of truth for a usable fixture's expected text:
        # the manifest `reference` and the generated `.txt` sidecar (RF-010).
        manifest = load_manifest(MANIFEST)

        # WHEN / THEN they must not drift apart.
        for spec in manifest.specs:
            if not spec.expect_usable:
                continue
            sidecar = spec.audio_path.with_suffix(".txt")
            self.assertTrue(sidecar.exists(), f"missing sidecar for {spec.name}: {sidecar}")
            self.assertEqual(
                sidecar.read_text(encoding="utf-8").strip(),
                (spec.reference or "").strip(),
                f"reference/sidecar drift for fixture '{spec.name}'",
            )


if __name__ == "__main__":
    unittest.main()
