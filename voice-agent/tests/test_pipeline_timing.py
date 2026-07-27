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
    TIME_TO_FIRST_AUDIO,
    TIME_TO_FIRST_AUDIO_SLICES,
    TTS_FIRST_AUDIO,
    VOICE_TO_FIRST_AUDIO,
    VOICE_TO_FIRST_AUDIO_SLICES,
    PipelineTimingReport,
    per_turn_timings,
    time_to_first_audio_report,
    time_to_first_audio_samples,
    voice_to_first_audio_report,
    voice_to_first_audio_samples,
)
from stt_validation.telemetry import Span  # noqa: E402
from tts_synthesis import FixtureTtsProvider  # noqa: E402
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice import ChannelEnvelope, WebVoiceEgress, WebVoiceIngress  # noqa: E402
from voice_pipeline.pipeline import run_batch_turn  # noqa: E402


def _span(name: str, duration_ms: float) -> Span:
    return Span(name=name, duration_ms=duration_ms, attributes={})


def _turn_spans(correlation_id: str, stt_ms: float, backend_ms: float, tts_ms: float) -> list[Span]:
    """One streaming turn: the three post-EOT slices that make up time_to_first_audio."""
    return [
        Span("stt.request", stt_ms, {"correlation_id": correlation_id}),
        Span("backend.first_token", backend_ms, {"correlation_id": correlation_id}),
        Span("voice.tts.first_audio", tts_ms, {"correlation_id": correlation_id}),
    ]


class _StubSttProvider:
    """Minimal STT provider: returns a canned transcript for any audio file."""

    name = "stub-stt"

    def transcribe(self, audio_path) -> str:  # noqa: ANN001 - matches SttProvider
        return "bonjour"


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

    def test_backend_slice_is_measured_from_first_token_span(self) -> None:
        # GIVEN a reviewed sample carrying the backend first-token span (TASK-WEB-003-E)
        spans = [_span("backend.first_token", float(value)) for value in range(1, 21)]

        # WHEN
        report = PipelineTimingReport.from_spans(spans)
        backend = next(s for s in report.slices if s.slice == BACKEND_FIRST_TOKEN)

        # THEN the backend slice is measured with percentiles, no longer a gap
        self.assertTrue(backend.measured)
        self.assertEqual(backend.report.count, 20)
        self.assertEqual(backend.report.p50_ms, 10.0)

    def test_backend_slice_falls_back_to_request_span(self) -> None:
        # GIVEN a batch sample with only the total backend.request span (no first_token)
        report = PipelineTimingReport.from_spans([_span("backend.request", 8.0)])
        backend = next(s for s in report.slices if s.slice == BACKEND_FIRST_TOKEN)

        # THEN the request span still measures the backend slice
        self.assertTrue(backend.measured)
        self.assertEqual(backend.report.count, 1)
        self.assertEqual(backend.report.p50_ms, 8.0)

    def test_backend_slice_prefers_first_token_over_request(self) -> None:
        # GIVEN both backend spans in the sample
        spans = [_span("backend.first_token", 3.0), _span("backend.request", 999.0)]

        # WHEN
        report = PipelineTimingReport.from_spans(spans)
        backend = next(s for s in report.slices if s.slice == BACKEND_FIRST_TOKEN)

        # THEN only the first-token span feeds the distribution (no mixing)
        self.assertTrue(backend.measured)
        self.assertEqual(backend.report.count, 1)
        self.assertEqual(backend.report.p50_ms, 3.0)

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


class TimeToFirstAudioCompositeTest(unittest.TestCase):
    """ADR-0018 pilot criterion: time_to_first_audio (EOT -> first playable frame)."""

    def test_composite_sums_the_post_eot_slices_of_one_turn(self) -> None:
        # GIVEN one streaming turn: STT tail 120 + backend 200 + TTS first-audio 180
        spans = _turn_spans("corr-1", stt_ms=120.0, backend_ms=200.0, tts_ms=180.0)

        # WHEN
        samples = time_to_first_audio_samples(spans)

        # THEN the composite is the sum of the three sequential slices
        self.assertEqual(samples, [500.0])

    def test_composite_component_slices_are_the_post_eot_path(self) -> None:
        # THEN end-of-turn (the acceptance boundary) and channel egress are excluded
        self.assertEqual(TIME_TO_FIRST_AUDIO_SLICES, (STT, BACKEND_FIRST_TOKEN, TTS_FIRST_AUDIO))

    def test_backend_request_span_feeds_composite_when_first_token_absent(self) -> None:
        # GIVEN a batch-style backend (only backend.request, no first_token)
        spans = [
            Span("stt.request", 100.0, {"correlation_id": "corr-1"}),
            Span("backend.request", 150.0, {"correlation_id": "corr-1"}),
            Span("voice.tts.first_audio", 90.0, {"correlation_id": "corr-1"}),
        ]

        # WHEN / THEN the request span still contributes the backend component
        self.assertEqual(time_to_first_audio_samples(spans), [340.0])

    def test_turns_of_different_calls_never_mix(self) -> None:
        # GIVEN two calls (distinct correlation ids), one turn each
        spans = _turn_spans("call-a", 100.0, 100.0, 100.0) + _turn_spans("call-b", 200.0, 200.0, 200.0)

        # WHEN
        samples = sorted(time_to_first_audio_samples(spans))

        # THEN each call yields its own composite, none blended across correlation ids
        self.assertEqual(samples, [300.0, 600.0])

    def test_multi_turn_call_reconstructs_each_turn_by_position(self) -> None:
        # GIVEN one call that answered two turns (same correlation id, recorded in order)
        spans = (
            _turn_spans("call-a", 100.0, 100.0, 100.0)
            + _turn_spans("call-a", 200.0, 200.0, 200.0)
        )

        # WHEN
        samples = time_to_first_audio_samples(spans)

        # THEN positional zip pairs the k-th span of each slice into turn k
        self.assertEqual(samples, [300.0, 600.0])

    def test_turn_missing_a_component_slice_is_skipped(self) -> None:
        # GIVEN a barge-in turn with no backend answer nor TTS in this call
        spans = [Span("stt.request", 100.0, {"correlation_id": "corr-1"})]

        # WHEN / THEN no truncated composite is produced
        self.assertEqual(time_to_first_audio_samples(spans), [])

    def test_report_computes_percentiles_and_flags_measured(self) -> None:
        # GIVEN 100 warm turns with a rising composite (i ms each component -> 3i total)
        spans: list[Span] = []
        for i in range(1, 101):
            spans += _turn_spans(f"corr-{i}", float(i), float(i), float(i))

        # WHEN
        composite = time_to_first_audio_report(spans)

        # THEN it is measured with nearest-rank percentiles over the composite samples
        self.assertEqual(composite.name, TIME_TO_FIRST_AUDIO)
        self.assertTrue(composite.measured)
        self.assertEqual(composite.report.count, 100)
        self.assertEqual(composite.report.p50_ms, 150.0)
        self.assertEqual(composite.report.p95_ms, 285.0)
        self.assertEqual(composite.report.p99_ms, 297.0)

    def test_report_is_not_measured_when_no_complete_turn_exists(self) -> None:
        # GIVEN only an STT span, no backend/TTS
        composite = time_to_first_audio_report([_span("stt.request", 5.0)])

        # THEN it is an explicit gap with a reason, not a fabricated zero
        self.assertFalse(composite.measured)
        self.assertIsNone(composite.report)
        self.assertTrue(composite.note)

    def test_composite_to_dict_is_json_serializable(self) -> None:
        # GIVEN a measured composite
        composite = time_to_first_audio_report(_turn_spans("corr-1", 100.0, 100.0, 100.0))

        # WHEN
        payload = composite.to_dict()

        # THEN the dict carries the component slices and the latency distribution
        self.assertEqual(payload["name"], TIME_TO_FIRST_AUDIO)
        self.assertTrue(payload["measured"])
        self.assertEqual(payload["component_slices"], list(TIME_TO_FIRST_AUDIO_SLICES))
        self.assertEqual(payload["latency"]["count"], 1)
        self.assertEqual(payload["latency"]["p50_ms"], 300.0)


class VoiceToFirstAudioCompositeTest(unittest.TestCase):
    """ADR-0029 mouth-to-ear: EOT hold + STT + backend + TTS + channel egress (TASK-WEB-014)."""

    def _m2e_turn(
        self,
        correlation_id: str,
        eot: float,
        stt: float,
        backend: float,
        tts: float,
        egress: float | None = None,
    ) -> list[Span]:
        attrs = {"correlation_id": correlation_id}
        spans = [
            Span("voice.end_of_turn", eot, attrs),
            Span("stt.request", stt, attrs),
            Span("backend.first_token", backend, attrs),
            Span("voice.tts.first_audio", tts, attrs),
        ]
        if egress is not None:
            spans.append(Span("web.voice.egress", egress, attrs))
        return spans

    def test_composite_folds_eot_hold_and_egress_into_the_sum(self) -> None:
        # GIVEN one turn: EOT 500 + STT 120 + backend 200 + TTS 180 + egress 5
        spans = self._m2e_turn("corr-1", eot=500.0, stt=120.0, backend=200.0, tts=180.0, egress=5.0)

        # WHEN / THEN the mouth-to-ear composite sums all five slices
        self.assertEqual(voice_to_first_audio_samples(spans), [1005.0])

    def test_component_slices_are_eot_plus_post_eot_path_plus_egress(self) -> None:
        # THEN the composite advertises all five ordered slices (egress last)
        self.assertEqual(
            VOICE_TO_FIRST_AUDIO_SLICES,
            (END_OF_TURN, STT, BACKEND_FIRST_TOKEN, TTS_FIRST_AUDIO, CHANNEL_EGRESS),
        )

    def test_egress_is_optional_and_folded_only_when_present(self) -> None:
        # GIVEN a turn with no egress span (batch-only had it; a bare streaming run may not)
        spans = self._m2e_turn("corr-1", eot=500.0, stt=100.0, backend=100.0, tts=100.0)

        # WHEN / THEN the composite is still computed over the required slices
        self.assertEqual(voice_to_first_audio_samples(spans), [800.0])
        # AND the report states the residual egress gap honestly
        report = voice_to_first_audio_report(spans)
        self.assertTrue(report.measured)
        self.assertIn("channel_egress not folded", report.note)

    def test_turn_missing_end_of_turn_is_skipped(self) -> None:
        # GIVEN a turn with the post-EOT path but no end-of-turn hold span
        spans = [
            Span("stt.request", 100.0, {"correlation_id": "c"}),
            Span("backend.first_token", 100.0, {"correlation_id": "c"}),
            Span("voice.tts.first_audio", 100.0, {"correlation_id": "c"}),
        ]

        # THEN no truncated mouth-to-ear composite is produced (EOT is required)
        self.assertEqual(voice_to_first_audio_samples(spans), [])
        self.assertFalse(voice_to_first_audio_report(spans).measured)

    def test_turns_of_different_calls_never_mix(self) -> None:
        # GIVEN two calls (distinct correlation ids), one turn each, both with egress
        spans = self._m2e_turn("a", 500.0, 100.0, 100.0, 100.0, egress=10.0) + self._m2e_turn(
            "b", 600.0, 200.0, 200.0, 200.0, egress=20.0
        )

        # THEN each call yields its own composite (810, 1220), never blended
        self.assertEqual(sorted(voice_to_first_audio_samples(spans)), [810.0, 1220.0])

    def test_egress_folded_per_turn_by_position_in_a_multi_turn_call(self) -> None:
        # GIVEN one call answering two turns, only the first carrying an egress span
        spans = (
            self._m2e_turn("a", 500.0, 100.0, 100.0, 100.0, egress=10.0)
            + self._m2e_turn("a", 500.0, 100.0, 100.0, 100.0)
        )

        # THEN turn 1 folds egress (810), turn 2 does not (800), and the note flags partial coverage
        self.assertEqual(sorted(voice_to_first_audio_samples(spans)), [800.0, 810.0])
        self.assertIn("1/2 turns", voice_to_first_audio_report(spans).note)

    def test_report_computes_percentiles_and_is_json_serializable(self) -> None:
        # GIVEN 100 warm turns with a rising composite
        spans: list[Span] = []
        for i in range(1, 101):
            spans += self._m2e_turn(f"c-{i}", float(i), float(i), float(i), float(i), egress=float(i))

        # WHEN
        composite = voice_to_first_audio_report(spans)
        payload = composite.to_dict()

        # THEN it is measured with nearest-rank percentiles over the composite (5i)
        self.assertEqual(composite.name, VOICE_TO_FIRST_AUDIO)
        self.assertTrue(composite.measured)
        self.assertEqual(payload["name"], VOICE_TO_FIRST_AUDIO)
        self.assertEqual(payload["latency"]["count"], 100)
        self.assertEqual(payload["latency"]["p50_ms"], 250.0)
        self.assertEqual(payload["latency"]["p95_ms"], 475.0)
        self.assertEqual(payload["component_slices"], list(VOICE_TO_FIRST_AUDIO_SLICES))

    def test_report_not_measured_when_no_complete_turn(self) -> None:
        # GIVEN only an end-of-turn span (no post-EOT path)
        composite = voice_to_first_audio_report([_span("voice.end_of_turn", 500.0)])

        # THEN it is an explicit gap with a reason, not a fabricated zero
        self.assertFalse(composite.measured)
        self.assertIsNone(composite.report)
        self.assertTrue(composite.note)


def _turn_with_id(
    correlation_id: str,
    turn_index: int,
    *,
    eot: float,
    stt: float,
    backend: float,
    tts: float,
    egress: float | None = None,
    message_id: str | None = None,
) -> list[Span]:
    """One streaming turn carrying the per-turn id (TASK-WEB-017)."""
    attrs = {
        "correlation_id": correlation_id,
        "turn_index": turn_index,
        "message_id": message_id or f"msg-{correlation_id}-{turn_index}",
    }
    spans = [
        Span("voice.end_of_turn", eot, attrs),
        Span("stt.request", stt, attrs),
        Span("backend.first_token", backend, attrs),
        Span("voice.tts.first_audio", tts, attrs),
    ]
    if egress is not None:
        spans.append(Span("web.voice.egress", egress, attrs))
    return spans


class PerTurnIdentityBucketingTest(unittest.TestCase):
    """TASK-WEB-017: a per-turn id splits a multi-turn streaming call robustly."""

    def test_barge_in_turn_missing_slices_does_not_desync_other_turns(self) -> None:
        # GIVEN a 3-turn streaming call where the MIDDLE turn was barged in (only an
        # end-of-turn + stt span, no backend/tts) — positional zip by correlation would
        # pair turn-1 STT with turn-3 backend; the per-turn id must prevent that.
        spans = (
            _turn_with_id("call", 1, eot=500.0, stt=100.0, backend=100.0, tts=100.0)
            + [
                Span("voice.end_of_turn", 500.0, {"correlation_id": "call", "turn_index": 2}),
                Span("stt.request", 999.0, {"correlation_id": "call", "turn_index": 2}),
            ]
            + _turn_with_id("call", 3, eot=500.0, stt=300.0, backend=300.0, tts=300.0)
        )

        # WHEN the composite is computed
        samples = sorted(time_to_first_audio_samples(spans))

        # THEN only the two complete turns contribute, each summing its OWN slices
        # (300 = 100*3, 900 = 300*3); the incomplete turn 2 is skipped, not blended
        self.assertEqual(samples, [300.0, 900.0])

    def test_mouth_to_ear_buckets_egress_by_turn_id_not_position(self) -> None:
        # GIVEN two turns of one call, only the SECOND carrying an egress span
        spans = _turn_with_id("call", 1, eot=500.0, stt=100.0, backend=100.0, tts=100.0) + _turn_with_id(
            "call", 2, eot=500.0, stt=100.0, backend=100.0, tts=100.0, egress=10.0
        )

        # WHEN the mouth-to-ear composite is computed
        samples = sorted(voice_to_first_audio_samples(spans))

        # THEN turn 1 has no egress (800) and turn 2 folds its own egress (810)
        self.assertEqual(samples, [800.0, 810.0])

    def test_per_turn_timings_yields_one_row_per_turn_with_composites(self) -> None:
        # GIVEN a two-turn streaming call
        spans = _turn_with_id("call", 1, eot=500.0, stt=100.0, backend=100.0, tts=100.0, egress=5.0) + _turn_with_id(
            "call", 2, eot=600.0, stt=200.0, backend=200.0, tts=200.0, egress=10.0
        )

        # WHEN the per-turn breakdown is built
        rows = per_turn_timings(spans)

        # THEN there is one row per turn, ordered, each with its own slices + composites
        self.assertEqual([r["turn_index"] for r in rows], [1, 2])
        self.assertNotEqual(rows[0]["message_id"], rows[1]["message_id"])
        self.assertEqual(rows[0]["time_to_first_audio_ms"], 300.0)  # 100*3
        self.assertEqual(rows[0]["voice_to_first_audio_ms"], 805.0)  # 500+300+5
        self.assertEqual(rows[1]["time_to_first_audio_ms"], 600.0)  # 200*3
        self.assertEqual(rows[1]["voice_to_first_audio_ms"], 1210.0)  # 600+600+10
        self.assertEqual(rows[0]["slices_ms"]["stt"], 100.0)

    def test_per_slice_report_keeps_one_sample_per_turn(self) -> None:
        # GIVEN two turns with distinct stt values on one call
        spans = _turn_with_id("call", 1, eot=1.0, stt=100.0, backend=1.0, tts=1.0) + _turn_with_id(
            "call", 2, eot=1.0, stt=200.0, backend=1.0, tts=1.0
        )

        # WHEN the per-slice report is built
        report = PipelineTimingReport.from_spans(spans)
        stt = next(s for s in report.slices if s.slice == STT)

        # THEN both turns' stt samples are kept (no overwrite): count 2, min 100 max 200
        self.assertEqual(stt.report.count, 2)
        self.assertEqual(stt.report.min_ms, 100.0)
        self.assertEqual(stt.report.max_ms, 200.0)

    def test_legacy_spans_without_turn_id_still_reconstruct_by_position(self) -> None:
        # GIVEN a pre-WEB-017 multi-turn call (same correlation, no turn_index)
        spans = _turn_spans("call", 100.0, 100.0, 100.0) + _turn_spans("call", 200.0, 200.0, 200.0)

        # WHEN the composite is computed
        # THEN the positional-zip fallback still separates the two turns
        self.assertEqual(sorted(time_to_first_audio_samples(spans)), [300.0, 600.0])


class PipelineTelemetryBridgeTest(unittest.IsolatedAsyncioTestCase):
    """The Pipecat batch pipeline must keep the US-036 slices measured (ST-5).

    Because the Pipecat services delegate to the same WebVoiceIngress / WebVoiceEgress
    with the shared TelemetryRecorder, a full turn through run_batch_turn (plus the
    transport's record_egress) emits the exact same spans the stdlib path does, so
    PipelineTimingReport measures the same slices.
    """

    async def test_full_turn_through_pipeline_measures_the_pipeline_slices(self) -> None:
        # GIVEN the real STT ingress + TTS egress wired with one telemetry recorder
        telemetry = TelemetryRecorder()
        ingress = WebVoiceIngress(_StubSttProvider())
        egress = WebVoiceEgress(FixtureTtsProvider())
        envelope = ChannelEnvelope.for_web_turn(correlation_id="corr-bridge")

        # WHEN a whole-utterance turn runs through the Pipecat batch pipeline
        result = await run_batch_turn(
            b"\x01\x02\x03\x04\x05\x06\x07\x08",
            envelope,
            ingress=ingress,
            egress=egress,
            telemetry=telemetry,
            received_ms=3.0,
        )
        # AND the transport reports the audio sent (owns the egress span)
        egress.record_egress(result.tts_response, envelope, telemetry, sent_ms=2.0)

        # THEN every US-036 slice is measured from the emitted spans, backend included
        report = PipelineTimingReport.from_spans(telemetry.spans())
        by_slice = {s.slice: s for s in report.slices}
        for name in (CHANNEL_INGRESS, STT, BACKEND_FIRST_TOKEN, TTS_FIRST_AUDIO, CHANNEL_EGRESS):
            self.assertTrue(by_slice[name].measured, f"{name} slice not measured")
        # AND the whole journey shares one correlation id (ingress -> ... -> egress)
        correlations = {s.attributes["correlation_id"] for s in telemetry.spans()}
        self.assertEqual(correlations, {"corr-bridge"})
        # AND the loop answered the transcript end to end (spoken reply produced)
        self.assertEqual(result.transcript_result.transcript, "bonjour")
        self.assertTrue(result.audio)


if __name__ == "__main__":
    unittest.main()
