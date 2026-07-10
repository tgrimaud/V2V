"""CLI reporting voice-journey timings by pipeline slice (US-036).

Replays a fixture manifest as a reviewed sample of turns on a single telemetry
recorder, then prints a per-slice p50/p95/p99 report. Slices that are not yet
instrumented (backend, TTS, egress) are reported as "measured": false so the
latency gaps are visible rather than hidden.
"""

import argparse
import json
from pathlib import Path

from .manifest import load_manifest
from .pipeline_timing import PipelineTimingReport
from .provider_factory import FIXTURE, PROVIDER_NAMES, build_provider
from .runner import SttValidationRunner
from .telemetry import TelemetryRecorder


def main() -> int:
    args = _parse_args()
    manifest = load_manifest(args.manifest)
    recorder = TelemetryRecorder()
    runner = SttValidationRunner(build_provider(args.provider), recorder)
    for spec in manifest.specs:
        runner.validate(spec.audio_path, spec.name)
    report = PipelineTimingReport.from_spans(recorder.spans())
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.measured_slices() else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report voice-journey timings by pipeline slice")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--provider", choices=PROVIDER_NAMES, default=FIXTURE)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
