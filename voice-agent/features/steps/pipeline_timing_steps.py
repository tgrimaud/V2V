from pathlib import Path

from behave import given, then, when

from stt_validation import TelemetryRecorder
from stt_validation.pipeline_timing import (
    BACKEND_FIRST_TOKEN,
    CHANNEL_EGRESS,
    CHANNEL_INGRESS,
    END_OF_TURN,
    STT,
    TTS_FIRST_AUDIO,
    PipelineTimingReport,
)
from web_voice import ChannelEnvelope, WebVoiceIngress

_INSTRUMENTED = (CHANNEL_INGRESS, STT)
_DEFERRED = (END_OF_TURN, BACKEND_FIRST_TOKEN, TTS_FIRST_AUDIO, CHANNEL_EGRESS)


class _SampleProvider:
    """Stub mic + STT provider so the sample exercises real span emission."""

    name = "stub-stt"

    def transcribe(self, audio_path: Path) -> str:
        audio_path.read_bytes()
        return "bonjour je voudrais comprendre ma facture"


@given("a reviewed sample of web voice turns captured on one recorder")
def step_reviewed_sample(context):
    context.telemetry = TelemetryRecorder()
    ingress = WebVoiceIngress(_SampleProvider())
    for index in range(5):
        envelope = ChannelEnvelope.for_web_turn(correlation_id=f"qa-timing-{index}")
        ingress.transcribe_turn(b"\x10\x20" * (200 + index * 40), envelope, context.telemetry)


@when("the pipeline timing report is built for the sample")
def step_build_report(context):
    context.report = PipelineTimingReport.from_spans(context.telemetry.spans())
    context.by_slice = {s.slice: s for s in context.report.slices}


@then("channel ingress, end-of-turn, STT, backend, TTS first audio and channel egress are reported separately")
def step_all_slices_present(context):
    expected = {CHANNEL_INGRESS, END_OF_TURN, STT, BACKEND_FIRST_TOKEN, TTS_FIRST_AUDIO, CHANNEL_EGRESS}
    assert set(context.by_slice) == expected, context.by_slice.keys()


@then("the instrumented slices expose p50, p95 and p99 for the reviewed sample")
def step_instrumented_percentiles(context):
    for name in _INSTRUMENTED:
        timing = context.by_slice[name]
        assert timing.measured, name
        report = timing.report
        assert report.count == 5, (name, report.count)
        assert report.p50_ms is not None and report.p95_ms is not None and report.p99_ms is not None


@then("the not-yet-instrumented slices are flagged as latency gaps to close")
def step_deferred_gaps(context):
    for name in _DEFERRED:
        timing = context.by_slice[name]
        assert not timing.measured, name
        assert timing.report is None, name
        assert timing.note, name
