import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stt_validation.pipeline_timing import (  # noqa: E402
    BACKEND_FIRST_TOKEN,
    CHANNEL_EGRESS,
    CHANNEL_INGRESS,
    END_OF_TURN,
    PIPELINE_SLICES,
    STT,
    TTS_FIRST_AUDIO,
    PipelineTimingReport,
)
from stt_validation.telemetry import Span  # noqa: E402


def _span(name: str, duration_ms: float) -> Span:
    return Span(name=name, duration_ms=duration_ms, attributes={})


class PipelineTimingReportTest(unittest.TestCase):
    def test_report_exposes_every_canonical_slice_in_journey_order(self) -> None:
        # GIVEN / WHEN
        report = PipelineTimingReport.from_spans([])

        # THEN
        self.assertEqual([s.slice for s in report.slices], list(PIPELINE_SLICES))

    def test_measured_slice_reports_percentiles_over_the_sample(self) -> None:
        # GIVEN a reviewed sample of STT turns
        spans = [_span("stt.request", float(value)) for value in range(1, 101)]

        # WHEN
        report = PipelineTimingReport.from_spans(spans)

        # THEN
        stt = next(s for s in report.slices if s.slice == STT)
        self.assertTrue(stt.measured)
        self.assertEqual(stt.report.count, 100)
        self.assertEqual(stt.report.p50_ms, 50.0)
        self.assertEqual(stt.report.p95_ms, 95.0)
        self.assertEqual(stt.report.p99_ms, 99.0)

    def test_deferred_slices_reported_as_not_measured_with_reason(self) -> None:
        # GIVEN a sample with only ingress + STT instrumented
        spans = [_span("web.voice.ingress", 3.0), _span("stt.request", 40.0)]

        # WHEN
        report = PipelineTimingReport.from_spans(spans)
        by_slice = {s.slice: s for s in report.slices}

        # THEN measured slices carry a distribution
        self.assertTrue(by_slice[CHANNEL_INGRESS].measured)
        self.assertTrue(by_slice[STT].measured)
        # AND uninstrumented slices are explicit gaps, not silent omissions
        for name in (BACKEND_FIRST_TOKEN, TTS_FIRST_AUDIO, CHANNEL_EGRESS):
            self.assertFalse(by_slice[name].measured)
            self.assertIsNone(by_slice[name].report)
            self.assertTrue(by_slice[name].note)

    def test_tts_first_audio_slice_is_measured_when_its_span_is_present(self) -> None:
        # GIVEN a reviewed sample carrying the TTS first-audio span (TASK-WEB-002)
        spans = [_span("voice.tts.first_audio", float(value)) for value in range(1, 21)]

        # WHEN
        report = PipelineTimingReport.from_spans(spans)
        tts = next(s for s in report.slices if s.slice == TTS_FIRST_AUDIO)

        # THEN the slice is measured with percentiles, not flagged as a gap
        self.assertTrue(tts.measured)
        self.assertEqual(tts.report.count, 20)
        self.assertEqual(tts.report.p50_ms, 10.0)

    def test_channel_egress_slice_is_measured_when_its_span_is_present(self) -> None:
        # GIVEN a sample carrying the web voice egress span (TASK-WEB-002)
        report = PipelineTimingReport.from_spans([_span("web.voice.egress", 7.0)])
        egress = next(s for s in report.slices if s.slice == CHANNEL_EGRESS)

        # THEN the egress slice is measured
        self.assertTrue(egress.measured)
        self.assertEqual(egress.report.count, 1)
        self.assertEqual(egress.report.p50_ms, 7.0)

    def test_end_of_turn_slice_is_measured_when_its_span_is_present(self) -> None:
        # GIVEN a reviewed sample carrying the end-of-turn span (TASK-STT-009)
        spans = [_span("voice.end_of_turn", float(value)) for value in range(1, 21)]

        # WHEN
        report = PipelineTimingReport.from_spans(spans)
        end_of_turn = next(s for s in report.slices if s.slice == END_OF_TURN)

        # THEN the slice is measured with percentiles, not flagged as a gap
        self.assertTrue(end_of_turn.measured)
        self.assertEqual(end_of_turn.report.count, 20)
        self.assertEqual(end_of_turn.report.p50_ms, 10.0)

    def test_end_of_turn_is_a_gap_only_when_its_span_is_absent(self) -> None:
        # GIVEN a sample without an end-of-turn span
        report = PipelineTimingReport.from_spans([_span("stt.request", 5.0)])
        by_slice = {s.slice: s for s in report.slices}

        # THEN it is a gap, and the note no longer points to a pending ticket
        self.assertFalse(by_slice[END_OF_TURN].measured)
        self.assertNotIn("TASK-STT-009", by_slice[END_OF_TURN].note)

    def test_channel_ingress_prefers_web_span_over_fixture_accept_span(self) -> None:
        # GIVEN both a web ingress span and a fixture accept span in the sample
        spans = [
            _span("web.voice.ingress", 5.0),
            _span("stt.audio.accept", 999.0),
        ]

        # WHEN
        report = PipelineTimingReport.from_spans(spans)
        ingress = next(s for s in report.slices if s.slice == CHANNEL_INGRESS)

        # THEN only the web ingress span feeds the distribution (no mixing)
        self.assertTrue(ingress.measured)
        self.assertEqual(ingress.report.count, 1)
        self.assertEqual(ingress.report.p50_ms, 5.0)

    def test_channel_ingress_falls_back_to_fixture_accept_span(self) -> None:
        # GIVEN a fixture-only run (no web ingress span)
        spans = [_span("stt.audio.accept", 2.0), _span("stt.request", 30.0)]

        # WHEN
        report = PipelineTimingReport.from_spans(spans)
        ingress = next(s for s in report.slices if s.slice == CHANNEL_INGRESS)

        # THEN the accept span provides the ingress distribution
        self.assertTrue(ingress.measured)
        self.assertEqual(ingress.report.count, 1)
        self.assertEqual(ingress.report.p50_ms, 2.0)

    def test_to_dict_is_json_serializable_and_flags_gaps(self) -> None:
        # GIVEN
        report = PipelineTimingReport.from_spans([_span("stt.request", 12.0)])

        # WHEN
        payload = report.to_dict()

        # THEN
        stt = next(s for s in payload["slices"] if s["slice"] == STT)
        tts = next(s for s in payload["slices"] if s["slice"] == TTS_FIRST_AUDIO)
        self.assertTrue(stt["measured"])
        self.assertEqual(stt["latency"]["count"], 1)
        # TTS is now instrumented (TASK-WEB-002): a gap in this sample means the
        # span was absent, and the note must no longer point to a pending ticket.
        self.assertFalse(tts["measured"])
        self.assertIsNone(tts["latency"])
        self.assertNotIn("TASK-WEB-002", tts["note"])
        self.assertIn("voice.tts.first_audio", tts["note"])


if __name__ == "__main__":
    unittest.main()
