"""Tests for the streaming-path latency report (TASK-WEB-009 / ADR-0018 evidence)."""

import json
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))
sys.path.insert(0, str(VOICE_AGENT_ROOT / "scripts"))

from streaming_latency_report import (  # noqa: E402
    build_streaming_report,
    parse_baseline,
    parse_telemetry_dumps,
)


def _call_dump(correlation_id: str, stt: float, backend: float, tts: float, *, barge_in: bool = False) -> str:
    """One server telemetry dump line for a single streaming turn."""
    attrs = {"correlation_id": correlation_id}
    spans = [
        {"name": "voice.end_of_turn", "duration_ms": 250.0, "attributes": attrs},
        {"name": "stt.request", "duration_ms": stt, "attributes": attrs},
        {"name": "backend.first_token", "duration_ms": backend, "attributes": attrs},
        {"name": "voice.tts.first_audio", "duration_ms": tts, "attributes": attrs},
    ]
    metrics = [
        {"name": "stt.time_to_first_partial_ms", "value": 90.0, "attributes": attrs},
        {"name": "stt.time_to_final_ms", "value": stt, "attributes": attrs},
        {"name": "tts.time_to_first_audio_ms", "value": tts, "attributes": attrs},
        {"name": "tts.time_to_last_audio_ms", "value": tts + 400.0, "attributes": attrs},
    ]
    if barge_in:
        metrics.append({"name": "voice.barge_in.count", "value": 1, "attributes": attrs})
    return json.dumps({"spans": spans, "events": [], "metrics": metrics}, sort_keys=True)


class ParseTelemetryDumpsTest(unittest.TestCase):
    def test_ignores_non_json_and_non_telemetry_lines(self) -> None:
        # GIVEN pipecat log noise interleaved with two call dumps
        lines = [
            "2026-07-16 22:00:00 | DEBUG | pipecat: worker started",
            _call_dump("c1", 120.0, 200.0, 180.0),
            "",
            '{"unrelated": "json object without spans"}',
            _call_dump("c2", 130.0, 210.0, 190.0),
        ]

        # WHEN
        spans, metrics, calls = parse_telemetry_dumps(lines)

        # THEN only the two telemetry dumps are parsed
        self.assertEqual(calls, 2)
        self.assertEqual(len(spans), 8)
        self.assertEqual({s.attributes["correlation_id"] for s in spans}, {"c1", "c2"})
        self.assertTrue(any(m.name == "stt.time_to_final_ms" for m in metrics))


class BuildStreamingReportTest(unittest.TestCase):
    def _report(self, *dumps: str, slo: float = 800.0) -> dict:
        spans, metrics, calls = parse_telemetry_dumps(list(dumps))
        return build_streaming_report(
            spans, metrics, calls=calls, channel="web", provider="gradium-streaming",
            warm=True, slo_p95_ms=slo,
        )

    def test_measures_post_eot_slices_and_flags_webrtc_gaps(self) -> None:
        # GIVEN two warm streaming calls
        report = self._report(
            _call_dump("c1", 120.0, 200.0, 180.0),
            _call_dump("c2", 130.0, 210.0, 190.0),
        )
        by_slice = {s["slice"]: s for s in report["per_slice"]["slices"]}

        # THEN the streaming path slices are measured
        for name in ("end_of_turn", "stt", "backend_first_token", "tts_first_audio"):
            self.assertTrue(by_slice[name]["measured"], f"{name} should be measured")
        # AND channel ingress/egress stay explicit gaps (batch-HTTP-only on WebRTC)
        self.assertFalse(by_slice["channel_ingress"]["measured"])
        self.assertFalse(by_slice["channel_egress"]["measured"])

    def test_composite_time_to_first_audio_is_reported_per_turn(self) -> None:
        # GIVEN two calls: composites 500 and 530
        report = self._report(
            _call_dump("c1", 120.0, 200.0, 180.0),
            _call_dump("c2", 130.0, 210.0, 190.0),
        )
        composite = report["time_to_first_audio"]

        # THEN the composite is measured over both turns
        self.assertTrue(composite["measured"])
        self.assertEqual(composite["latency"]["count"], 2)
        self.assertEqual(composite["latency"]["max_ms"], 530.0)

    def test_gate_passes_when_p95_below_criterion(self) -> None:
        # GIVEN a warm sample well under 800 ms
        report = self._report(_call_dump("c1", 120.0, 200.0, 180.0), slo=800.0)

        # THEN the ADR-0018 gate passes with a positive margin
        gate = report["adr_0018_gate"]
        self.assertEqual(gate["status"], "pass")
        self.assertEqual(gate["criterion_p95_ms"], 800.0)
        self.assertGreater(gate["margin_ms"], 0)

    def test_gate_fails_when_p95_exceeds_criterion(self) -> None:
        # GIVEN a slow turn (composite 1500 ms)
        report = self._report(_call_dump("slow", 500.0, 500.0, 500.0), slo=800.0)

        # THEN the gate fails honestly with a negative margin
        gate = report["adr_0018_gate"]
        self.assertEqual(gate["status"], "fail")
        self.assertEqual(gate["measured_p95_ms"], 1500.0)
        self.assertLess(gate["margin_ms"], 0)

    def test_gate_not_measured_when_no_complete_turn(self) -> None:
        # GIVEN a dump with only an end-of-turn span (no answer/tts)
        dump = json.dumps(
            {"spans": [{"name": "voice.end_of_turn", "duration_ms": 250.0, "attributes": {"correlation_id": "x"}}],
             "events": [], "metrics": []},
            sort_keys=True,
        )
        report = self._report(dump)

        # THEN the gate is a documented gap, not a silent pass/fail
        self.assertEqual(report["adr_0018_gate"]["status"], "not_measured")
        self.assertFalse(report["time_to_first_audio"]["measured"])

    def test_metric_distributions_and_barge_in_count(self) -> None:
        # GIVEN two calls, one with a barge-in
        report = self._report(
            _call_dump("c1", 120.0, 200.0, 180.0, barge_in=True),
            _call_dump("c2", 130.0, 210.0, 190.0),
        )

        # THEN streaming metric distributions are summarised and barge-ins counted
        distributions = report["metric_distributions"]
        self.assertEqual(distributions["stt.time_to_first_partial_ms"]["count"], 2)
        self.assertIsNotNone(distributions["tts.time_to_first_audio_ms"])
        self.assertEqual(report["barge_in_count"], 1)
        self.assertEqual(report["sample"]["calls"], 2)
        self.assertEqual(report["sample"]["turns_with_first_audio"], 2)

    def test_provider_baseline_absent_by_default(self) -> None:
        # GIVEN a report built without a provider baseline
        report = self._report(_call_dump("c1", 120.0, 200.0, 180.0))

        # THEN the provider_baseline section is an explicit null, not a fabricated value
        self.assertIsNone(report["provider_baseline"])

    def test_provider_baseline_reports_delta(self) -> None:
        # GIVEN two turns whose measured TTS first-audio is 300 and 500 ms
        spans, metrics, calls = parse_telemetry_dumps(
            [_call_dump("c1", 120.0, 200.0, 300.0), _call_dump("c2", 130.0, 210.0, 500.0)]
        )
        baseline = parse_baseline("min=186.36,p50=329.53,p90=364.19,p95=364.19")

        # WHEN a Gradium-style provider baseline is supplied
        report = build_streaming_report(
            spans, metrics, calls=calls, channel="web", provider="gradium-streaming",
            warm=True, tts_baseline=baseline, tts_baseline_source="Gradium dashboard 2026-07-16",
        )

        # THEN the delta is measured minus provider at the overlapping percentiles
        section = report["provider_baseline"]
        self.assertEqual(section["metric"], "tts.time_to_first_audio_ms")
        self.assertEqual(section["source"], "Gradium dashboard 2026-07-16")
        self.assertEqual(section["provider"]["p90_ms"], 364.19)  # provider extra kept, informational
        self.assertEqual(section["measured"]["p50_ms"], 300.0)
        self.assertEqual(section["measured"]["p95_ms"], 500.0)
        # p50 delta = 300 - 329.53 (our median is faster here); p95 = 500 - 364.19
        self.assertAlmostEqual(section["delta_ms"]["p50_ms"], -29.53, places=3)
        self.assertAlmostEqual(section["delta_ms"]["p95_ms"], 135.81, places=3)
        # p90 has no measured counterpart, so no delta entry for it
        self.assertNotIn("p90_ms", section["delta_ms"])

    def test_provider_baseline_with_no_measured_samples(self) -> None:
        # GIVEN a turn that produced no TTS first-audio metric (STT-only dump)
        dump = json.dumps(
            {"spans": [{"name": "voice.end_of_turn", "duration_ms": 250.0, "attributes": {"correlation_id": "x"}}],
             "events": [], "metrics": []},
            sort_keys=True,
        )
        spans, metrics, calls = parse_telemetry_dumps([dump])
        baseline = parse_baseline("min=186.36,p50=329.53,p95=364.19")

        # WHEN a provider baseline is supplied but there is nothing to compare against
        report = build_streaming_report(
            spans, metrics, calls=calls, channel="web", provider="gradium-streaming",
            warm=True, tts_baseline=baseline, tts_baseline_source="Gradium dashboard 2026-07-16",
        )

        # THEN the provider is echoed but measured/delta are explicit nulls (no crash, no fabricated delta)
        section = report["provider_baseline"]
        self.assertEqual(section["provider"]["p50_ms"], 329.53)
        self.assertIsNone(section["measured"])
        self.assertIsNone(section["delta_ms"])


class ParseBaselineTest(unittest.TestCase):
    def test_parses_percentiles_and_normalises_ms_suffix(self) -> None:
        # GIVEN a provider baseline spec with mixed keys
        baseline = parse_baseline(" min=186.36, p50=329.53 ,p95=364.19")

        # THEN keys are normalised to the *_ms convention with float values
        self.assertEqual(baseline, {"min_ms": 186.36, "p50_ms": 329.53, "p95_ms": 364.19})

    def test_rejects_malformed_entry(self) -> None:
        # GIVEN a spec missing a value
        # THEN parsing fails loudly rather than guessing
        with self.assertRaises(ValueError):
            parse_baseline("p50=329.53,p95")


if __name__ == "__main__":
    unittest.main()
