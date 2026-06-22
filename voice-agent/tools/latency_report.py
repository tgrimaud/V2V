#!/usr/bin/env python3
"""Aggregate [LATENCY] log lines into per-step p50/p95 baselines.

Parses lines of the form:
    [LATENCY] step=<name> ms=<value> [extra=...]

emitted by the backend (vector_search, llm_first_token, llm_total) and the
voice agent bridge (stt, tts, time_to_first_audio, turn_total).

Usage:
    # From a captured log file (backend + bridge merged or separate):
    python tools/latency_report.py backend.log bridge.log

    # From a live tail / pipe:
    tail -f bridge.out | python tools/latency_report.py -

SLO reference: time_to_first_audio p95 < 800 ms.
"""

import re
import sys
from statistics import mean

LATENCY_RE = re.compile(r"\[LATENCY\]\s+step=(?P<step>\S+)\s+ms=(?P<ms>\d+(?:\.\d+)?)")

SLO_MS = {"time_to_first_audio": 800}

STEP_ORDER = [
    "stt",
    "vector_search",
    "llm_first_token",
    "time_to_first_audio",
    "tts",
    "llm_total",
    "turn_total",
]


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (pct in [0, 100])."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, round(pct / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def collect(streams) -> dict[str, list[float]]:
    samples: dict[str, list[float]] = {}
    for stream in streams:
        for line in stream:
            match = LATENCY_RE.search(line)
            if match:
                samples.setdefault(match.group("step"), []).append(float(match.group("ms")))
    return samples


def open_streams(paths: list[str]):
    if not paths:
        return [sys.stdin]
    streams = []
    for path in paths:
        streams.append(sys.stdin if path == "-" else open(path, encoding="utf-8"))
    return streams


def main() -> int:
    samples = collect(open_streams(sys.argv[1:]))
    if not samples:
        print("No [LATENCY] lines found.", file=sys.stderr)
        return 1

    header = f"{'step':<22}{'n':>6}{'p50':>9}{'p95':>9}{'min':>9}{'max':>9}{'mean':>9}  SLO"
    print(header)
    print("-" * len(header))

    ordered_steps = [s for s in STEP_ORDER if s in samples]
    ordered_steps += [s for s in samples if s not in STEP_ORDER]

    for step in ordered_steps:
        values = samples[step]
        p50 = percentile(values, 50)
        p95 = percentile(values, 95)
        slo = SLO_MS.get(step)
        slo_flag = ""
        if slo is not None:
            slo_flag = f"<{slo}  {'OK' if p95 < slo else 'FAIL'}"
        print(
            f"{step:<22}{len(values):>6}{p50:>9.0f}{p95:>9.0f}"
            f"{min(values):>9.0f}{max(values):>9.0f}{mean(values):>9.0f}  {slo_flag}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
