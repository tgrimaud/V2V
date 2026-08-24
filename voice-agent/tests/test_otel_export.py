"""Offline tests for the env-gated voice OTLP export (TASK-OBS-001).

Export translation is validated with an in-memory span exporter, so no collector or
network is required. The gate is verified to keep export a strict no-op by default.
"""

import unittest

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from voice_common.otel_export import export_recorder, otlp_export_enabled
from voice_common.telemetry import TelemetryRecorder


class _BrokenRecorder:
    """A recorder whose accessors raise — exercises the export_recorder guard."""

    def spans(self):
        raise RuntimeError("boom")

    def events(self):
        return []

    def metrics(self):
        return []


def _recorder_with_turn() -> TelemetryRecorder:
    recorder = TelemetryRecorder()
    recorder.begin_turn(correlation_id="corr-1", conversation_id="conv-1", turn_index=2)
    recorder.span("stt.request", 120.0, provider="gradium", outcome="success")
    recorder.span("voice.tts.first_audio", 300.0, provider="gradium")
    recorder.record("voice.call_end", reason="customer_farewell")
    recorder.metric("voice.stt.wer", 0.0)
    return recorder


class OtlpGateTest(unittest.TestCase):
    def test_disabled_by_default_without_env(self):
        # GIVEN no OTEL env vars
        # WHEN checking the gate / exporting
        # THEN export is a no-op and reports disabled
        self.assertFalse(otlp_export_enabled({}))
        self.assertFalse(export_recorder(_recorder_with_turn(), env={}))

    def test_enabled_by_otlp_endpoint(self):
        self.assertTrue(otlp_export_enabled({"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"}))

    def test_enabled_by_voice_flag(self):
        self.assertTrue(otlp_export_enabled({"VOICE_OTEL_EXPORT": "1"}))
        self.assertFalse(otlp_export_enabled({"VOICE_OTEL_EXPORT": "0"}))


class OtlpExportTranslationTest(unittest.TestCase):
    def test_recorder_is_translated_to_root_and_child_spans(self):
        # GIVEN a per-turn recorder and an in-memory exporter (bypasses the env gate)
        exporter = InMemorySpanExporter()
        # WHEN exporting
        exported = export_recorder(_recorder_with_turn(), span_exporter=exporter)
        # THEN it reports success and produces a root span + one child per recorded span
        self.assertTrue(exported)
        spans = exporter.get_finished_spans()
        names = [s.name for s in spans]
        self.assertIn("voice.turn", names)
        self.assertIn("stt.request", names)
        self.assertIn("voice.tts.first_audio", names)

        root = next(s for s in spans if s.name == "voice.turn")
        # identity baggage is hoisted onto the root span
        self.assertEqual(root.attributes.get("correlation_id"), "corr-1")
        self.assertEqual(root.attributes.get("conversation_id"), "conv-1")
        self.assertEqual(root.attributes.get("turn_index"), 2)
        # metrics land as metric.* attributes and events as span events
        self.assertIn("metric.voice.stt.wer", root.attributes)
        self.assertIn("voice.call_end", [e.name for e in root.events])

        child = next(s for s in spans if s.name == "stt.request")
        self.assertEqual(child.attributes.get("provider"), "gradium")

    def test_turn_uses_the_trace_id_derived_from_correlation_id(self):
        # GIVEN a per-turn recorder (correlation_id="corr-1") and an in-memory exporter
        from voice_common.trace_context import derive_trace_ids

        exporter = InMemorySpanExporter()
        # WHEN exporting
        self.assertTrue(export_recorder(_recorder_with_turn(), span_exporter=exporter))
        spans = exporter.get_finished_spans()
        # THEN the root and every child share the trace id derived from the correlation id
        # (the same id http_backend injects as traceparent) so the turn is one cross-tier trace
        derived_trace_id, derived_span_id = derive_trace_ids("corr-1")
        root = next(s for s in spans if s.name == "voice.turn")
        self.assertEqual(root.context.trace_id, derived_trace_id)
        # the root's parent is the derived span id — the backend spans hang off the same id
        self.assertEqual(root.parent.span_id, derived_span_id)
        for span in spans:
            self.assertEqual(span.context.trace_id, derived_trace_id)

    def test_export_never_raises_on_translation_error(self):
        # GIVEN a recorder that raises while being read
        exporter = InMemorySpanExporter()
        # WHEN exporting
        # THEN the error is swallowed and export reports failure (telemetry never breaks a call)
        self.assertFalse(export_recorder(_BrokenRecorder(), span_exporter=exporter))


if __name__ == "__main__":
    unittest.main()
