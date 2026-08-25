"""Tests for the shared per-call telemetry payload (TASK-WEB-030 AC#2).

The streaming paths (WebRTC + WebSocket) have no per-turn HTTP response, so the end-of-call
dump is the only latency/QA evidence. `build_payload` must always carry the canonical
per-slice journey timing: every slice present with a measured true/false flag, so a slice
with no span is marked `measured=false` (never silently omitted) and a partial call is still
readable per slice under one correlation id.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice.session_telemetry import build_payload  # noqa: E402

# The six canonical journey slices reported in flow order (US-036 / ADR-0028).
CANONICAL_SLICES = {
    "channel_ingress",
    "end_of_turn",
    "stt",
    "backend_first_token",
    "tts_first_audio",
    "channel_egress",
}


class SessionTelemetryPayloadTest(unittest.TestCase):
    def test_payload_carries_spans_events_metrics_and_pipeline_timing(self):
        # GIVEN a recorder with a couple of measured slices on one turn
        telemetry = TelemetryRecorder()
        telemetry.span("voice.end_of_turn", 120.0, correlation_id="corr-1")
        telemetry.span("stt.request", 300.0, correlation_id="corr-1")
        telemetry.record("stt.transcript.final", correlation_id="corr-1")
        telemetry.metric("voice.ws.active_sessions", 1.0, correlation_id="corr-1")
        # WHEN the per-call payload is built
        payload = build_payload(telemetry)
        # THEN it carries the raw snapshot plus the canonical per-slice timing block
        self.assertIn("spans", payload)
        self.assertIn("events", payload)
        self.assertIn("metrics", payload)
        self.assertIn("pipeline_timing", payload)

    def test_every_canonical_slice_is_present_with_a_measured_flag(self):
        # GIVEN a partial turn: only end_of_turn + stt measured
        telemetry = TelemetryRecorder()
        telemetry.span("voice.end_of_turn", 120.0, correlation_id="corr-1")
        telemetry.span("stt.request", 300.0, correlation_id="corr-1")
        # WHEN the payload is built
        timing = build_payload(telemetry)["pipeline_timing"]
        slices = timing["slices"] if isinstance(timing, dict) and "slices" in timing else timing
        # THEN every canonical slice is present (missing ones marked measured=false, not omitted)
        by_name = {s["slice"]: s for s in slices}
        self.assertEqual(set(by_name) & CANONICAL_SLICES, CANONICAL_SLICES)
        self.assertTrue(by_name["end_of_turn"]["measured"])
        self.assertTrue(by_name["stt"]["measured"])
        self.assertFalse(by_name["backend_first_token"]["measured"])
        self.assertFalse(by_name["channel_egress"]["measured"])


if __name__ == "__main__":
    unittest.main()
