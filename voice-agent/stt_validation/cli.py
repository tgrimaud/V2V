import argparse
import json
from pathlib import Path

from .providers import FixtureSttProvider
from .runner import SttValidationRunner
from .telemetry import TelemetryRecorder


def main() -> int:
    args = _parse_args()
    telemetry = TelemetryRecorder()
    runner = SttValidationRunner(FixtureSttProvider(), telemetry)
    result = runner.validate(args.audio_path, args.correlation_id)
    payload = {
        "result": result.to_dict(),
        "events": [event.__dict__ for event in telemetry.events()],
        "metrics": [metric.__dict__ for metric in telemetry.metrics()],
        "logs": [log.__dict__ for log in telemetry.logs()],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.outcome.value == "success" else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an STT audio fixture")
    parser.add_argument("audio_path", type=Path)
    parser.add_argument("--correlation-id", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
