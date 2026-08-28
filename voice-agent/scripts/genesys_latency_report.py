"""Genesys Audio Connector per-leg latency + capacity report (TASK-WEB-043).

The Genesys counterpart of `streaming_latency_report.py`. It consumes the same server
stderr telemetry dump lines (one JSON object per call, `{"spans": [...], "metrics": [...]}`)
emitted by `genesys_timing.genesys_log_telemetry`, and reports over the sample:

- the Genesys per-leg p50/p95 (`genesys_pipeline_timing`): transcode in/out + STT + backend
  + TTS measured; the Genesys-cloud ingress/egress + Architect fork stay explicit
  `measured=false` gaps (never omitted, US-036 rule);
- the concurrency ceiling + peak simultaneous sessions observed;
- the WS 1013 backpressure refusal count (capacity refusals made visible);
- the explicit ADR-0029 re-score verdict (gated while the cloud legs need the live org).

Collect the sample, then run:

    .venv/bin/python scripts/genesys_latency_report.py \
        --input /tmp/genesys-telemetry.jsonl --provider gradium --warm
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.streaming_latency_report import parse_telemetry_dumps  # noqa: E402
from web_voice.envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL  # noqa: E402
from web_voice.genesys_timing import build_genesys_report  # noqa: E402


def _read_lines(source: str) -> Iterable[str]:
    if source == "-":
        return sys.stdin
    return Path(source).read_text(encoding="utf-8").splitlines()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genesys Audio Connector per-leg + capacity latency report (TASK-WEB-043)"
    )
    parser.add_argument("--input", default="-", help="telemetry dump file (JSON lines); '-' = stdin")
    parser.add_argument("--channel", default=GENESYS_AUDIO_CONNECTOR_CHANNEL)
    parser.add_argument("--provider", default="gradium")
    warm_group = parser.add_mutually_exclusive_group()
    warm_group.add_argument("--warm", dest="warm", action="store_true", default=True)
    warm_group.add_argument("--cold", dest="warm", action="store_false")
    parser.add_argument("--note", default=None)
    args = parser.parse_args()

    spans, metrics, calls = parse_telemetry_dumps(_read_lines(args.input))
    report = build_genesys_report(
        spans, metrics, calls=calls, channel=args.channel, provider=args.provider,
        warm=args.warm, note=args.note,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
