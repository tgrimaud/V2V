from pathlib import Path

from behave import given, then, when

from stt_validation import SttOutcome, TelemetryRecorder
from web_voice import ChannelEnvelope, WebVoiceIngress

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
