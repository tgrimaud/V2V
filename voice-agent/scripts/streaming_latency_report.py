"""Streaming-path latency report (TASK-WEB-009, feeds ADR-0018 evidence).

The streaming counterpart to `turn_latency_sample.py`. That script drives the
batch turn in-process; the streaming WebRTC loop cannot be driven that way (it
needs a real transport + live STT/TTS providers), so its telemetry is emitted
server-side: `WebRtcSignalingService` prints one JSON line per call on teardown
(`{"spans": [...], "events": [...], "metrics": [...]}`).

This tool consumes those server-stderr telemetry lines from a reviewed sample of
    10|warm streaming calls and reports, over the whole sample:

- the US-036 per-slice p50/p95/p99 (`PipelineTimingReport`);
- selected streaming metric distributions (time_to_first_partial, time_to_final,
  streamed tts_first_audio, tts_last_audio);
- the ADR-0018 composite `time_to_first_audio` (end-of-turn -> first playable
  frame) p50/p95/p99, plus the pilot-acceptance gate (`p95 < 800 ms`);
- barge-in count observed in the sample;
- an optional provider baseline for the TTS first-audio metric: when the
  provider publishes its own "time to first audio buffer" percentiles (e.g. the
  Gradium dashboard), pass them via `--tts-baseline` to report the per-percentile
  delta (measured minus provider) our path adds on top of the provider.

Slices that never appear in the sample (e.g. `channel_ingress` / `channel_egress`
    20|are batch-HTTP-only, never emitted on the WebRTC transport) stay explicit gaps
rather than being silently dropped.

Collect the sample, then run:

    # capture server telemetry lines while running warm streaming calls
    ... > /tmp/streaming-telemetry.jsonl
    .venv/bin/python scripts/streaming_latency_report.py \
        --input /tmp/streaming-telemetry.jsonl \
        --channel web --provider gradium-streaming --warm
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_common.pipeline_timing import (  # noqa: E402
    PipelineTimingReport,
    per_turn_timings,
    time_to_first_audio_report,
    voice_to_first_audio_report,
)
from voice_common.telemetry import LatencyReport, MetricSample, Span  # noqa: E402

DEFAULT_SLO_P95_MS = 800.0
# ADR-0029 pilot acceptance: mouth-to-ear p95 <= 1.5 s (primary) + a
# time_to_first_audio p95 <= 1.2 s engineering sub-target. TASK-WEB-014 is the
# measurement prerequisite that instruments the mouth-to-ear composite so the gate
# can actually be evaluated (not just the middle-of-chain composite).
ADR_0029_MOUTH_TO_EAR_P95_MS = 1500.0
ADR_0029_TTFA_P95_MS = 1200.0

# Streaming metric names surfaced as distributions (emitted by the streaming STT /
# TTS processors). Barge-in is a counter, handled separately.
_METRIC_DISTRIBUTIONS: tuple[str, ...] = (
    "stt.time_to_first_partial_ms",
    "stt.time_to_final_ms",
    "tts.time_to_first_audio_ms",
    "tts.time_to_last_audio_ms",
)
_BARGE_IN_METRIC = "voice.barge_in.count"

# Metric compared against a published provider baseline (time to first audio buffer).
_BASELINE_METRIC = "tts.time_to_first_audio_ms"
# Percentiles we can subtract (present in both our LatencyReport and a typical
# provider baseline). Provider extras (e.g. p90) stay informational, no delta.
_BASELINE_DELTA_KEYS: tuple[str, ...] = ("min_ms", "p50_ms", "p95_ms", "p99_ms")


def parse_baseline(spec: str) -> dict[str, float]:
    """Parse 'min=186.36,p50=329.53,p90=364.19,p95=364.19' into {'min_ms': ..., ...}."""
    baseline: dict[str, float] = {}
    for pair in spec.split(","):
        pair = pair.strip()
        if not pair:
            continue
        key, sep, value = pair.partition("=")
        key, value = key.strip().lower(), value.strip()
        if not sep or not key or not value:
            raise ValueError(f"invalid baseline entry {pair!r}: expected key=value")
        baseline[key if key.endswith("_ms") else f"{key}_ms"] = float(value)
    return baseline


def _provider_baseline(
    metrics: list[MetricSample],
    baseline: dict[str, float] | None,
    source: str | None,
) -> dict[str, Any] | None:
    """Compare our measured TTS first-audio distribution to a provider baseline."""
    if not baseline:
        return None
    samples = [m.value for m in metrics if m.name == _BASELINE_METRIC]
    measured = LatencyReport.from_samples(samples).to_dict() if samples else None
    delta: dict[str, float] = {}
    for key in _BASELINE_DELTA_KEYS:
        provider_value, measured_value = baseline.get(key), (measured or {}).get(key)
        if provider_value is not None and measured_value is not None:
            delta[key] = round(measured_value - provider_value, 3)
    return {
        "metric": _BASELINE_METRIC,
        "source": source,
        "provider": baseline,
        "measured": measured,
        "delta_ms": delta or None,
    }


def _span_from_dict(raw: dict[str, Any]) -> Span:
    return Span(
        name=raw["name"],
        duration_ms=float(raw["duration_ms"]),
        attributes=raw.get("attributes") or {},
    )


def _metric_from_dict(raw: dict[str, Any]) -> MetricSample:
    return MetricSample(
        name=raw["name"],
        value=float(raw["value"]),
        attributes=raw.get("attributes") or {},
    )


def parse_telemetry_dumps(lines: Iterable[str]) -> tuple[list[Span], list[MetricSample], int]:
    """Extract spans + metrics from server telemetry dump lines.

    Server stderr interleaves pipecat/loguru text with the JSON telemetry dumps, so
    each line is tried as JSON and only dicts carrying a "spans" key are treated as a
    call dump. Returns the flattened spans, metrics and the number of call dumps.
    """
    spans: list[Span] = []
    metrics: list[MetricSample] = []
    calls = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or "spans" not in payload:
            continue
        calls += 1
        spans.extend(_span_from_dict(s) for s in payload.get("spans", []))
        metrics.extend(_metric_from_dict(m) for m in payload.get("metrics", []))
    return spans, metrics, calls


def _metric_distributions(metrics: list[MetricSample]) -> dict[str, Any]:
    by_name: dict[str, list[float]] = {}
    for metric in metrics:
        by_name.setdefault(metric.name, []).append(metric.value)
    distributions: dict[str, Any] = {}
    for name in _METRIC_DISTRIBUTIONS:
        samples = by_name.get(name)
        distributions[name] = (
            LatencyReport.from_samples(samples).to_dict() if samples else None
        )
    return distributions


def _barge_in_count(metrics: list[MetricSample]) -> int:
    return int(sum(m.value for m in metrics if m.name == _BARGE_IN_METRIC))


def _p95_gate(composite_report, criterion_p95_ms: float) -> dict[str, Any]:
    """Evaluate one composite's p95 against a `<=` criterion (not_measured-safe)."""
    if not composite_report.measured or composite_report.report is None:
        return {"criterion_p95_ms": criterion_p95_ms, "status": "not_measured", "margin_ms": None}
    p95 = composite_report.report.p95_ms
    passed = p95 is not None and p95 <= criterion_p95_ms
    return {
        "criterion_p95_ms": criterion_p95_ms,
        "measured_p95_ms": p95,
        "status": "pass" if passed else "fail",
        "margin_ms": round(criterion_p95_ms - p95, 3) if p95 is not None else None,
    }


def _slo_gate(composite_report, slo_p95_ms: float) -> dict[str, Any]:
    """ADR-0018 pilot acceptance gate on time_to_first_audio p95 (strict `<`)."""
    if not composite_report.measured or composite_report.report is None:
        return {"criterion_p95_ms": slo_p95_ms, "status": "not_measured", "margin_ms": None}
    p95 = composite_report.report.p95_ms
    passed = p95 is not None and p95 < slo_p95_ms
    return {
        "criterion_p95_ms": slo_p95_ms,
        "measured_p95_ms": p95,
        "status": "pass" if passed else "fail",
        "margin_ms": round(slo_p95_ms - p95, 3) if p95 is not None else None,
    }


def _adr_0029_gate(
    mouth_to_ear,
    time_to_first_audio,
    *,
    mouth_to_ear_p95_ms: float,
    ttfa_p95_ms: float,
) -> dict[str, Any]:
    """ADR-0029 pilot gate: mouth-to-ear p95 (primary) + time_to_first_audio p95 (sub).

    Overall go/no-go is a pass only when both sub-criteria pass; if either is
    `not_measured` the overall status stays `not_measured` (never a silent pass)."""
    primary = _p95_gate(mouth_to_ear, mouth_to_ear_p95_ms)
    engineering = _p95_gate(time_to_first_audio, ttfa_p95_ms)
    statuses = {primary["status"], engineering["status"]}
    if "not_measured" in statuses:
        overall = "not_measured"
    elif statuses == {"pass"}:
        overall = "pass"
    else:
        overall = "fail"
    return {
        "status": overall,
        "mouth_to_ear_p95": primary,
        "time_to_first_audio_p95": engineering,
    }


def build_streaming_report(
    spans: list[Span],
    metrics: list[MetricSample],
    *,
    calls: int,
    channel: str,
    provider: str,
    warm: bool,
    slo_p95_ms: float = DEFAULT_SLO_P95_MS,
    mouth_to_ear_p95_ms: float = ADR_0029_MOUTH_TO_EAR_P95_MS,
    ttfa_p95_ms: float = ADR_0029_TTFA_P95_MS,
    note: str | None = None,
    tts_baseline: dict[str, float] | None = None,
    tts_baseline_source: str | None = None,
) -> dict[str, Any]:
    per_slice = PipelineTimingReport.from_spans(spans)
    composite = time_to_first_audio_report(spans)
    mouth_to_ear = voice_to_first_audio_report(spans)
    return {
        "sample": {
            "calls": calls,
            "turns_with_first_audio": composite.report.count if composite.report else 0,
            "turns_with_mouth_to_ear": mouth_to_ear.report.count if mouth_to_ear.report else 0,
            "channel": channel,
            "provider": provider,
            "warm": warm,
            "environment": "co-located dev host",
            "note": note,
        },
        "per_slice": per_slice.to_dict(),
        # Per-turn breakdown (TASK-WEB-017): one row per (correlation_id, turn_index) so a
        # multi-turn streaming call is readable turn by turn — turns no longer collapse
        # under a shared span name. Empty on pre-WEB-017 samples (no per-turn id).
        "per_turn": per_turn_timings(spans),
        "metric_distributions": _metric_distributions(metrics),
        "barge_in_count": _barge_in_count(metrics),
        "time_to_first_audio": composite.to_dict(),
        "voice_to_first_audio": mouth_to_ear.to_dict(),
        "adr_0018_gate": _slo_gate(composite, slo_p95_ms),
        "adr_0029_gate": _adr_0029_gate(
            mouth_to_ear,
            composite,
            mouth_to_ear_p95_ms=mouth_to_ear_p95_ms,
            ttfa_p95_ms=ttfa_p95_ms,
        ),
        "provider_baseline": _provider_baseline(metrics, tts_baseline, tts_baseline_source),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Streaming WebRTC per-slice + time_to_first_audio latency report (TASK-WEB-009)"
    )
    parser.add_argument(
        "--input",
        default="-",
        help="server telemetry dump file (JSON lines); '-' reads stdin (default)",
    )
    parser.add_argument("--channel", default="web")
    parser.add_argument("--provider", default="gradium-streaming")
    warm_group = parser.add_mutually_exclusive_group()
    warm_group.add_argument("--warm", dest="warm", action="store_true", default=True)
    warm_group.add_argument("--cold", dest="warm", action="store_false")
    parser.add_argument("--slo-p95-ms", type=float, default=DEFAULT_SLO_P95_MS)
    parser.add_argument(
        "--mouth-to-ear-p95-ms",
        type=float,
        default=ADR_0029_MOUTH_TO_EAR_P95_MS,
        help="ADR-0029 primary pilot criterion (mouth-to-ear p95 <= this, ms)",
    )
    parser.add_argument(
        "--ttfa-p95-ms",
        type=float,
        default=ADR_0029_TTFA_P95_MS,
        help="ADR-0029 engineering sub-target (time_to_first_audio p95 <= this, ms)",
    )
    parser.add_argument("--note", default=None)
    parser.add_argument(
        "--tts-baseline",
        default=None,
        help=(
            "provider TTS first-audio (time to first audio buffer) baseline percentiles, "
            "e.g. 'min=186.36,p50=329.53,p90=364.19,p95=364.19'; adds a per-percentile delta comparison"
        ),
    )
    parser.add_argument(
        "--tts-baseline-source",
        default=None,
        help="human label for the baseline source, e.g. 'Gradium dashboard 2026-07-16'",
    )
    args = parser.parse_args()

    if args.input == "-":
        lines: Iterable[str] = sys.stdin
    else:
        lines = Path(args.input).read_text(encoding="utf-8").splitlines()
    spans, metrics, calls = parse_telemetry_dumps(lines)

    tts_baseline = parse_baseline(args.tts_baseline) if args.tts_baseline else None
    report = build_streaming_report(
        spans,
        metrics,
        calls=calls,
        channel=args.channel,
        provider=args.provider,
        warm=args.warm,
        slo_p95_ms=args.slo_p95_ms,
        mouth_to_ear_p95_ms=args.mouth_to_ear_p95_ms,
        ttfa_p95_ms=args.ttfa_p95_ms,
        note=args.note,
        tts_baseline=tts_baseline,
        tts_baseline_source=args.tts_baseline_source,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
