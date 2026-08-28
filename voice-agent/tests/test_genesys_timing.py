"""TASK-WEB-043: the Genesys Audio Connector per-leg latency + capacity report.

Covers the four ticket bullets at the aggregation layer (transport wiring lives in
`test_genesys_app.py`, exporter parenting in `test_genesys_otel_export.py`):

- per-leg slices: the runtime-measurable Genesys legs (transcode in/out + STT/backend/TTS)
  are reported, while the Genesys-cloud legs stay explicit `measured=false` gaps with a
  reason (never omitted, US-036 rule) and no distribution mixes across span names;
- per-channel concurrency (peak + ceiling) derived from the Genesys active-sessions gauge;
- backpressure (WS 1013) surfaced as an aggregatable refusal count;
- an explicit, gated ADR-0029 re-score verdict (never a silent pass).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_common.telemetry import MetricSample, Span  # noqa: E402
from web_voice.envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL  # noqa: E402
from web_voice.genesys_config import ACTIVE_SESSIONS_METRIC, SESSION_REJECTED_METRIC  # noqa: E402
from web_voice.genesys_framing import TRANSCODE_IN_SPAN, TRANSCODE_OUT_SPAN  # noqa: E402
from web_voice.genesys_timing import (  # noqa: E402
    ARCHITECT_FORK,
    GENESYS_EGRESS,
    GENESYS_INGRESS,
    GENESYS_PIPELINE_SLICES,
    TRANSCODE_IN,
    TRANSCODE_OUT,
    build_genesys_report,
    genesys_backpressure,
    genesys_concurrency,
    genesys_pipeline_timing,
)


def _genesys_turn_spans() -> list[Span]:
    """One instrumented Genesys turn: transcode in/out + the shared STT/backend/TTS spans."""
    channel = {"channel": GENESYS_AUDIO_CONNECTOR_CHANNEL, "correlation_id": "conv-1"}
    return [
        Span(TRANSCODE_IN_SPAN, 3.2, {**channel, "codec": "L16"}),
        Span("stt.request", 1100.0, {"correlation_id": "conv-1"}),
        Span("backend.first_token", 420.0, {"correlation_id": "conv-1"}),
        Span("voice.tts.first_audio", 300.0, {"correlation_id": "conv-1", "outcome": "success"}),
        Span(TRANSCODE_OUT_SPAN, 2.9, {**channel, "codec": "L16"}),
    ]


def _gauge(value: float, max_sessions: int, outcome: str) -> MetricSample:
    return MetricSample(
        ACTIVE_SESSIONS_METRIC,
        value,
        {"channel": GENESYS_AUDIO_CONNECTOR_CHANNEL, "outcome": outcome, "max_sessions": max_sessions},
    )


class GenesysPipelineTimingTest(unittest.TestCase):
    def test_every_genesys_leg_is_present_in_flow_order(self) -> None:
        # GIVEN / WHEN an empty sample is reported
        report = genesys_pipeline_timing([])

        # THEN all nine Genesys legs appear, in flow order, none omitted
        self.assertEqual(tuple(s.slice for s in report.slices), GENESYS_PIPELINE_SLICES)

    def test_runtime_measurable_legs_are_measured_from_their_spans(self) -> None:
        # GIVEN one instrumented Genesys turn
        report = genesys_pipeline_timing(_genesys_turn_spans())
        by_name = {s.slice: s for s in report.slices}

        # WHEN / THEN the transcode + STT/backend/TTS legs are measured from their spans
        self.assertTrue(by_name[TRANSCODE_IN].measured)
        self.assertEqual(by_name[TRANSCODE_IN].report.p95_ms, 3.2)
        self.assertTrue(by_name[TRANSCODE_OUT].measured)
        self.assertEqual(by_name[TRANSCODE_OUT].report.p95_ms, 2.9)
        self.assertTrue(by_name["stt"].measured)
        self.assertTrue(by_name["backend_first_token"].measured)
        self.assertTrue(by_name["tts_first_audio"].measured)

    def test_cloud_legs_stay_measured_false_with_a_reason(self) -> None:
        # GIVEN the same instrumented turn (no cloud-leg spans exist in the runtime)
        by_name = {s.slice: s for s in genesys_pipeline_timing(_genesys_turn_spans()).slices}

        # WHEN / THEN the Genesys-cloud legs are explicit measured=false gaps with a reason
        for leg in (GENESYS_INGRESS, ARCHITECT_FORK, GENESYS_EGRESS):
            self.assertFalse(by_name[leg].measured)
            self.assertIsNone(by_name[leg].report)
            self.assertIn("live-org", by_name[leg].note)

    def test_end_of_turn_note_points_to_the_native_events_ticket(self) -> None:
        # GIVEN a turn with no in-house end-of-turn span (native events own it on this path)
        by_name = {s.slice: s for s in genesys_pipeline_timing(_genesys_turn_spans()).slices}

        # WHEN / THEN the end_of_turn leg is measured=false and names TASK-WEB-042
        self.assertFalse(by_name["end_of_turn"].measured)
        self.assertIn("TASK-WEB-042", by_name["end_of_turn"].note)


class GenesysConcurrencyTest(unittest.TestCase):
    def test_reports_ceiling_and_peak_from_the_active_sessions_gauge(self) -> None:
        # GIVEN gauge samples peaking at 3 concurrent sessions under a ceiling of 3
        metrics = [_gauge(1.0, 3, "accepted"), _gauge(3.0, 3, "accepted"), _gauge(2.0, 3, "closed")]

        # WHEN the concurrency block is built
        concurrency = genesys_concurrency(metrics)

        # THEN it reports the ceiling and the observed peak
        self.assertEqual(concurrency["ceiling"], 3)
        self.assertEqual(concurrency["peak_active_sessions"], 3.0)

    def test_ignores_non_genesys_channel_gauges(self) -> None:
        # GIVEN a WS gauge (different channel) alongside a Genesys gauge
        ws_gauge = MetricSample(
            "voice.ws.active_sessions", 9.0, {"channel": "web_voice", "max_sessions": 1}
        )
        metrics = [ws_gauge, _gauge(1.0, 3, "accepted")]

        # WHEN / THEN the WS gauge does not leak into the Genesys peak
        self.assertEqual(genesys_concurrency(metrics)["peak_active_sessions"], 1.0)


class GenesysBackpressureTest(unittest.TestCase):
    def test_counts_ws_1013_refusals_from_the_rejection_metric(self) -> None:
        # GIVEN two capacity refusals recorded as the backpressure counter
        refusal = MetricSample(
            SESSION_REJECTED_METRIC,
            1.0,
            {"channel": GENESYS_AUDIO_CONNECTOR_CHANNEL, "reason": "capacity", "max_sessions": 3},
        )

        # WHEN the backpressure block is built
        backpressure = genesys_backpressure([refusal, refusal])

        # THEN both refusals are counted under the rejection metric name
        self.assertEqual(backpressure["metric"], SESSION_REJECTED_METRIC)
        self.assertEqual(backpressure["refused_sessions"], 2)

    def test_reports_zero_refusals_when_none_occurred(self) -> None:
        # GIVEN / WHEN no refusal metric in the sample
        # THEN the count is zero (not missing)
        self.assertEqual(genesys_backpressure([])["refused_sessions"], 0)


class GenesysReportTest(unittest.TestCase):
    def test_adr_0029_verdict_is_gated_not_a_silent_pass(self) -> None:
        # GIVEN a fully instrumented runtime turn (cloud legs still unmeasured)
        report = build_genesys_report(_genesys_turn_spans(), [_gauge(1.0, 3, "accepted")], calls=1)

        # WHEN / THEN the ADR-0029 re-score is explicitly gated and names TASK-WEB-042
        self.assertEqual(report["adr_0029_gate"]["status"], "not_measured")
        self.assertIn("TASK-WEB-042", report["adr_0029_gate"]["reason"])

    def test_report_assembles_all_four_observability_blocks(self) -> None:
        # GIVEN a sample with spans + a gauge + a refusal
        refusal = MetricSample(
            SESSION_REJECTED_METRIC, 1.0, {"channel": GENESYS_AUDIO_CONNECTOR_CHANNEL}
        )
        # WHEN the report is built
        report = build_genesys_report(
            _genesys_turn_spans(), [_gauge(2.0, 3, "accepted"), refusal], calls=1
        )
        # THEN per-leg, concurrency, backpressure and the ADR-0029 verdict are all present
        self.assertIn("per_leg", report)
        self.assertEqual(report["concurrency"]["peak_active_sessions"], 2.0)
        self.assertEqual(report["backpressure"]["refused_sessions"], 1)
        self.assertEqual(report["sample"]["channel"], GENESYS_AUDIO_CONNECTOR_CHANNEL)


class GenesysPerCallPayloadTest(unittest.TestCase):
    def test_per_call_payload_carries_the_genesys_legs_not_the_web_legs(self) -> None:
        # GIVEN a recorder for one instrumented Genesys call
        from voice_common.telemetry import TelemetryRecorder
        from web_voice.genesys_timing import genesys_pipeline_timing
        from web_voice.session_telemetry import build_payload

        telemetry = TelemetryRecorder()
        for span in _genesys_turn_spans():
            telemetry.span(span.name, span.duration_ms, **span.attributes)

        # WHEN the per-call payload is built with the Genesys per-leg builder
        payload = build_payload(telemetry, pipeline_timing=genesys_pipeline_timing)
        legs = {s["slice"]: s for s in payload["pipeline_timing"]["slices"]}

        # THEN the block carries the Genesys legs (transcode in measured), not the web legs
        self.assertIn(TRANSCODE_IN, legs)
        self.assertTrue(legs[TRANSCODE_IN]["measured"])
        self.assertFalse(legs[GENESYS_INGRESS]["measured"])
        self.assertNotIn("channel_ingress", legs)


if __name__ == "__main__":
    unittest.main()
