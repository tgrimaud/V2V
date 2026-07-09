import argparse
import json
from pathlib import Path

from .models import SttOutcome
from .provider_factory import FIXTURE, PROVIDER_NAMES, build_provider
from .runner import SttValidationRunner
from .telemetry import LatencyReport, TelemetryRecorder


def main() -> int:
    args = _parse_args()
    telemetry = TelemetryRecorder()
    runner = SttValidationRunner(build_provider(args.provider), telemetry)

    results = [runner.validate(path, _correlation_id(args, index)) for index, path in enumerate(args.audio_path)]
    stt_samples = [result.stt_request_ms for result in results]

    payload = {
        "results": [result.to_dict() for result in results],
        "latency_report": LatencyReport.from_samples(stt_samples).to_dict(),
        "spans": [span.__dict__ for span in telemetry.spans()],
        "events": [event.__dict__ for event in telemetry.events()],
        "metrics": [metric.__dict__ for metric in telemetry.metrics()],
        "logs": [log.__dict__ for log in telemetry.logs()],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if all(result.outcome is SttOutcome.SUCCESS for result in results) else 1


def _correlation_id(args: argparse.Namespace, index: int) -> str | None:
    if args.correlation_id is None:
        return None
    if len(args.audio_path) == 1:
        return args.correlation_id
    return f"{args.correlation_id}-{index}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate one or more STT audio fixtures")
    parser.add_argument("audio_path", type=Path, nargs="+")
    parser.add_argument("--correlation-id", default=None)
    parser.add_argument("--provider", choices=PROVIDER_NAMES, default=FIXTURE)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
