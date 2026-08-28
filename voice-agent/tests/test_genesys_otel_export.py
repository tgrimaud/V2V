"""TASK-WEB-043: the Genesys per-channel telemetry is consumable by the OTLP exporter.

Confirms the WEB-041 Genesys instrumentation (per-leg transcode spans, per-channel gauge,
backpressure counter, deterministic `conversationId -> traceparent`) is actually exported
under ONE trace: every span the exporter emits for a Genesys call shares the trace id
derived from the Genesys conversationId (no orphan roots), the per-channel label is hoisted
onto the turn root, and the gauge/backpressure metrics land as root attributes so a
collector can filter and count them per channel.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

from voice_common.otel_export import export_recorder  # noqa: E402
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from voice_common.trace_context import derive_trace_ids  # noqa: E402
from web_voice.envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL  # noqa: E402
from web_voice.genesys_config import (  # noqa: E402
    ACTIVE_SESSIONS_METRIC,
    SESSION_REJECTED_METRIC,
    SESSION_STARTED_EVENT,
)
from web_voice.genesys_framing import TRANSCODE_IN_SPAN  # noqa: E402

GENESYS_CONVERSATION_ID = "genesys-conv-42"


def _genesys_call_recorder() -> TelemetryRecorder:
    """A recorder shaped like one Genesys call: session event + transcode span + gauge."""
    recorder = TelemetryRecorder()
    channel = GENESYS_AUDIO_CONNECTOR_CHANNEL
    recorder.record(SESSION_STARTED_EVENT, correlation_id=GENESYS_CONVERSATION_ID, channel=channel)
    recorder.span(TRANSCODE_IN_SPAN, 3.2, correlation_id=GENESYS_CONVERSATION_ID, channel=channel, codec="L16")
    recorder.span("stt.request", 100.0, correlation_id=GENESYS_CONVERSATION_ID)
    recorder.metric(
        ACTIVE_SESSIONS_METRIC, 1.0, correlation_id=GENESYS_CONVERSATION_ID,
        channel=channel, outcome="accepted", max_sessions=3,
    )
    return recorder


class GenesysOtlpExportTest(unittest.TestCase):
    def test_genesys_spans_share_the_traceparent_derived_from_the_conversation_id(self) -> None:
        # GIVEN a Genesys call recorder and an in-memory exporter (bypasses the env gate)
        exporter = InMemorySpanExporter()
        # WHEN it is exported
        self.assertTrue(export_recorder(_genesys_call_recorder(), span_exporter=exporter))
        spans = exporter.get_finished_spans()
        # THEN every exported span shares the trace id derived from the Genesys conversationId
        # (one trace: Genesys leg + runtime + backend), and the transcode leg is not an orphan
        derived_trace_id, _ = derive_trace_ids(GENESYS_CONVERSATION_ID)
        self.assertIn(TRANSCODE_IN_SPAN, [s.name for s in spans])
        for span in spans:
            self.assertEqual(span.context.trace_id, derived_trace_id)

    def test_per_channel_label_and_metrics_are_hoisted_onto_the_turn_root(self) -> None:
        # GIVEN a Genesys call recorder
        exporter = InMemorySpanExporter()
        # WHEN exported
        export_recorder(_genesys_call_recorder(), span_exporter=exporter)
        root = next(s for s in exporter.get_finished_spans() if s.name == "voice.turn")
        # THEN the per-channel label is on the root and the gauge is a filterable root attribute
        self.assertEqual(root.attributes.get("channel"), GENESYS_AUDIO_CONNECTOR_CHANNEL)
        self.assertIn(f"metric.{ACTIVE_SESSIONS_METRIC}", root.attributes)

    def test_backpressure_refusal_metric_is_exported_as_a_root_attribute(self) -> None:
        # GIVEN a refusal recorder (a WS 1013 capacity refusal carries no session spans)
        recorder = TelemetryRecorder()
        recorder.metric(
            SESSION_REJECTED_METRIC, 1.0, correlation_id="genesys-conv-99",
            channel=GENESYS_AUDIO_CONNECTOR_CHANNEL, reason="capacity", max_sessions=3,
        )
        exporter = InMemorySpanExporter()
        # WHEN exported
        export_recorder(recorder, span_exporter=exporter)
        root = next(s for s in exporter.get_finished_spans() if s.name == "voice.turn")
        # THEN the backpressure counter is visible on the exported turn (capacity refusals visible)
        self.assertIn(f"metric.{SESSION_REJECTED_METRIC}", root.attributes)


if __name__ == "__main__":
    unittest.main()
