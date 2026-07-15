from pathlib import Path

from behave import given, then, when

from stt_validation import SttOutcome, TelemetryRecorder
from stt_validation.pipeline_timing import (
    CHANNEL_EGRESS,
    CHANNEL_INGRESS,
    STT,
    TTS_FIRST_AUDIO,
    PipelineTimingReport,
)
from tts_synthesis import FixtureTtsProvider
from web_voice import ChannelEnvelope, WebVoiceEgress, WebVoiceIngress
from web_voice.runtime import PipecatTurnProcessor, StdlibTurnProcessor

SECRET_PATH = "/private/customer/invoice-9931.pcm"


class _StubProvider:
    """Stands in for the mic + STT provider so Behave can assert the ingress contract."""

    name = "stub-stt"

    def __init__(self, transcript: str = "", error: Exception | None = None) -> None:
        self._transcript = transcript
        self._error = error

    def transcribe(self, audio_path: Path) -> str:
        audio_path.read_bytes()
        if self._error is not None:
            raise self._error
        return self._transcript


def _span(context, name):
    return next(span for span in context.telemetry.spans() if span.name == name)


@given("a web voice turn with captured PCM audio")
def step_web_turn_audio(context):
    context.telemetry = TelemetryRecorder()
    context.ingress = WebVoiceIngress(_StubProvider(transcript="bonjour je paye trop cher ce mois"))
    context.audio = b"\x11\x22" * 320
    context.envelope = ChannelEnvelope.for_web_turn(correlation_id="qa-web-ok")


@given("a web voice turn whose STT provider fails with a filesystem path")
def step_web_turn_failure(context):
    context.telemetry = TelemetryRecorder()
    context.ingress = WebVoiceIngress(_StubProvider(error=FileNotFoundError(f"missing {SECRET_PATH}")))
    context.audio = b"\x00" * 128
    context.envelope = ChannelEnvelope.for_web_turn(correlation_id="qa-web-fail")


@when("the web voice ingress transcribes the turn")
def step_ingress_transcribe(context):
    context.result = context.ingress.transcribe_turn(context.audio, context.envelope, context.telemetry)


@then("the transcript is returned to the page")
def step_transcript_returned(context):
    assert context.result.outcome is SttOutcome.SUCCESS, context.result.outcome
    assert context.result.transcript.strip(), "expected a non-empty transcript"


@then("a real channel-ingress span records the received audio bytes")
def step_ingress_span(context):
    span = _span(context, "web.voice.ingress")
    assert span.attributes["channel"] == "web_voice"
    assert span.attributes["audio_bytes"] == len(context.audio), span.attributes["audio_bytes"]


@then("the STT slice latency and correlation id are observable")
def step_latency_and_correlation(context):
    assert context.result.correlation_id == "qa-web-ok"
    assert context.result.stt_request_ms >= 0.0
    assert _span(context, "stt.request").attributes["correlation_id"] == "qa-web-ok"


@then("no transcript is invented on the page")
def step_no_invented_transcript(context):
    assert context.result.outcome is SttOutcome.FAILED
    assert context.result.transcript == ""


@then("a stable error code and sanitized reason are exposed")
def step_error_code_exposed(context):
    assert context.result.error_code, "expected a stable error code"
    assert context.result.error_reason, "expected a sanitized reason"


@then("the sanitized reason contains no filesystem path")
def step_no_path_in_reason(context):
    reason = context.result.error_reason or ""
    assert "/" not in reason and "\\" not in reason, reason
    assert SECRET_PATH not in reason


@given("a web voice turn processed by the pipecat runtime")
def step_pipecat_runtime(context):
    context.telemetry = TelemetryRecorder()
    ingress = WebVoiceIngress(_StubProvider(transcript="bonjour je paye trop cher ce mois"))
    egress = WebVoiceEgress(FixtureTtsProvider())
    context.processor = PipecatTurnProcessor(ingress, egress)
    context.audio = b"\x11\x22" * 320
    context.envelope = ChannelEnvelope.for_web_turn(correlation_id="qa-web-pipecat")


@when("the runtime runs the full voice turn")
def step_run_full_turn(context):
    context.turn = context.processor.run_turn(context.audio, context.envelope, context.telemetry)
    context.processor.record_egress(context.turn.tts_response, context.envelope, context.telemetry, sent_ms=1.0)


@then("the phrase is transcribed, answered by the backend and spoken back")
def step_answered_and_spoken(context):
    assert context.turn.transcript_result.outcome is SttOutcome.SUCCESS, context.turn.transcript_result.outcome
    assert context.turn.answer_result is not None, "expected a backend answer"
    assert context.turn.answer_result.text.strip(), "expected a non-empty answer"
    assert context.turn.tts_response is not None and context.turn.tts_response.wav, "expected spoken WAV"
    assert context.turn.tts_response.wav[:4] == b"RIFF"


@then("the spoken reply is the backend answer, not the transcript")
def step_reply_is_answer(context):
    transcript = context.turn.transcript_result.transcript
    answer = context.turn.answer_result.text
    assert answer != transcript, "the reply must be the backend answer, not an echo of the transcript"


@then("the pipeline slices are observable via telemetry")
def step_pipeline_slices_observable(context):
    report = PipelineTimingReport.from_spans(context.telemetry.spans())
    by_slice = {s.slice: s for s in report.slices}
    for name in (CHANNEL_INGRESS, STT, TTS_FIRST_AUDIO, CHANNEL_EGRESS):
        assert by_slice[name].measured, f"{name} slice not measured"


def _runtime_wav(processor_cls, audio, envelope) -> bytes:
    ingress = WebVoiceIngress(_StubProvider(transcript="bonjour"))
    egress = WebVoiceEgress(FixtureTtsProvider())
    processor = processor_cls(ingress, egress)
    result = processor.run_turn(audio, envelope, TelemetryRecorder())
    return result.tts_response.wav


@given("the same captured audio for both runtimes")
def step_same_audio_both_runtimes(context):
    context.audio = b"\x05\x06" * 320
    context.envelope = ChannelEnvelope.for_web_turn(correlation_id="qa-web-parity")


@when("the turn is processed by the stdlib and pipecat runtimes")
def step_process_both_runtimes(context):
    context.stdlib_wav = _runtime_wav(StdlibTurnProcessor, context.audio, context.envelope)
    context.pipecat_wav = _runtime_wav(PipecatTurnProcessor, context.audio, context.envelope)


@then("both runtimes produce identical WAV output")
def step_identical_wav(context):
    assert context.stdlib_wav == context.pipecat_wav, "runtimes diverged"
    assert context.stdlib_wav and context.stdlib_wav[:4] == b"RIFF"
