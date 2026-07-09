import argparse
import json
from pathlib import Path

from .manifest import load_manifest
from .providers import FixtureSttProvider
from .quality import evaluate_fixture_set
from .runner import SttValidationRunner
from .telemetry import TelemetryRecorder


def main() -> int:
    args = _parse_args()
    manifest = load_manifest(args.manifest)
    runner = SttValidationRunner(FixtureSttProvider(), TelemetryRecorder())
    report = evaluate_fixture_set(
        runner,
        manifest.specs,
        manifest.expected_categories,
        manifest.quality_threshold,
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.ready else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate STT transcription quality across a fixture manifest")
    parser.add_argument("manifest", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
