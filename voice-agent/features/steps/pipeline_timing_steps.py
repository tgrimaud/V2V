import array
import sys
from pathlib import Path

from behave import given, then, when

from tts_synthesis import FixtureTtsProvider
from voice_common.pipeline_timing import (
    BACKEND_FIRST_TOKEN,
    CHANNEL_EGRESS,
    CHANNEL_INGRESS,
    END_OF_TURN,
    STT,
    TTS_FIRST_AUDIO,
    PipelineTimingReport,
)
from voice_common.telemetry import TelemetryRecorder
from web_voice import ChannelEnvelope, WebVoiceEgress, WebVoiceIngress
from web_voice.runtime import StdlibTurnProcessor

_INSTRUMENTED = (CHANNEL_INGRESS, END_OF_TURN, STT)
_DEFERRED = (BACKEND_FIRST_TOKEN, TTS_FIRST_AUDIO, CHANNEL_EGRESS)


class _SampleProvider:
    """Stub mic + STT provider so the sample exercises real span emission."""

    name = "stub-stt"

    def transcribe(self, audio_path: Path) -> str:
        audio_path.read_bytes()
        return "bonjour je voudrais comprendre ma facture"


def _turn_audio(speech_ms: float, silence_ms: float, sample_rate: int = 16000) -> bytes:
    # Speech followed by a trailing-silence window so end-of-turn is detected.
    speech = [8000] * int(sample_rate * speech_ms / 1000)
    silence = [0] * int(sample_rate * silence_ms / 1000)
    data = array.array("h", speech + silence)
    if sys.byteorder == "big":
        data.byteswap()
    return data.tobytes()


@given("a reviewed sample of web voice turns captured on one recorder")
def step_reviewed_sample(context):
    context.telemetry = TelemetryRecorder()
    ingress = WebVoiceIngress(_SampleProvider())
    for index in range(5):
        envelope = ChannelEnvelope.for_web_turn(correlation_id=f"qa-timing-{index}")
        audio = _turn_audio(speech_ms=150 + index * 20, silence_ms=500)
        ingress.transcribe_turn(audio, envelope, context.telemetry)


@given("a reviewed sample of full web voice turns through the backend bridge")
def step_full_turn_sample(context):
    context.telemetry = TelemetryRecorder()
    processor = StdlibTurnProcessor(WebVoiceIngress(_SampleProvider()), WebVoiceEgress(FixtureTtsProvider()))
    for index in range(5):
        envelope = ChannelEnvelope.for_web_turn(correlation_id=f"qa-full-{index}")
        audio = _turn_audio(speech_ms=150 + index * 20, silence_ms=500)
        result = processor.run_turn(audio, envelope, context.telemetry, received_ms=1.0 + index * 0.5)
        processor.record_egress(result.tts_response, envelope, context.telemetry, sent_ms=1.0 + index * 0.5)


@given("a full web voice turn through the backend bridge")
def step_single_full_turn(context):
    context.telemetry = TelemetryRecorder()
    context.correlation_id = "qa-backend-e2e"
    processor = StdlibTurnProcessor(WebVoiceIngress(_SampleProvider()), WebVoiceEgress(FixtureTtsProvider()))
    envelope = ChannelEnvelope.for_web_turn(correlation_id=context.correlation_id)
    audio = _turn_audio(speech_ms=200, silence_ms=500)
    result = processor.run_turn(audio, envelope, context.telemetry, received_ms=1.0)
    processor.record_egress(result.tts_response, envelope, context.telemetry, sent_ms=2.0)


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


@then("the TTS first audio and channel egress slices expose p50, p95 and p99 for the reviewed sample")
def step_voice_out_percentiles(context):
    for name in (TTS_FIRST_AUDIO, CHANNEL_EGRESS):
        timing = context.by_slice[name]
        assert timing.measured, name
        report = timing.report
        assert report.count == 5, (name, report.count)
        assert report.p50_ms is not None and report.p95_ms is not None and report.p99_ms is not None


@then("the backend slice is reported measured, no longer a latency gap")
def step_backend_measured(context):
    backend = context.by_slice[BACKEND_FIRST_TOKEN]
    assert backend.measured, "backend slice should be measured once the bridge is wired"
    assert backend.report is not None and backend.report.count >= 1


@then("no implemented slice remains a latency gap to close")
def step_no_implemented_gap(context):
    for name in (CHANNEL_INGRESS, END_OF_TURN, STT, BACKEND_FIRST_TOKEN, TTS_FIRST_AUDIO, CHANNEL_EGRESS):
        assert context.by_slice[name].measured, name


@then("every recorded slice shares one correlation id")
def step_single_correlation_id(context):
    correlations = {s.attributes["correlation_id"] for s in context.telemetry.spans()}
    assert correlations == {context.correlation_id}, correlations
