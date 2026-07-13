from pathlib import Path

from behave import given, then, when

from tts_synthesis import FixtureTtsProvider, TtsOutcome, TtsSynthesisRunner
from voice_common.telemetry import TelemetryRecorder

REFERENCE_TEXTS = Path(__file__).resolve().parents[2] / "fixtures" / "tts" / "reference-texts.txt"
SECRET_TOKEN = "gsk_live_supersecret_TTS_key_0099"


def _load_reference_texts() -> list[str]:
    lines = REFERENCE_TEXTS.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


class _RaisingProvider:
    name = "boom-tts"
    audio_format = "pcm_16000"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def synthesize(self, text: str) -> bytes:
        raise self._exc


@given("the offline TTS provider and the reference response texts")
def step_offline_provider_and_texts(context):
    context.telemetry = TelemetryRecorder()
    context.runner = TtsSynthesisRunner(FixtureTtsProvider(), context.telemetry)
    context.texts = _load_reference_texts()
    assert context.texts, "expected at least one reference text"


@given("the offline TTS provider")
def step_offline_provider(context):
    context.telemetry = TelemetryRecorder()
    context.runner = TtsSynthesisRunner(FixtureTtsProvider(), context.telemetry)


@given("a TTS provider that fails carrying a secret token")
def step_failing_provider(context):
    context.telemetry = TelemetryRecorder()
    provider = _RaisingProvider(RuntimeError(f"auth rejected key {SECRET_TOKEN} invalid"))
    context.runner = TtsSynthesisRunner(provider, context.telemetry)


@when("the voice runtime synthesizes each reference text")
def step_synthesize_each(context):
    context.results = [
        context.runner.synthesize(text, f"qa-tts-{index}")
        for index, text in enumerate(context.texts)
    ]


@when("the voice runtime synthesizes an empty response text")
def step_synthesize_empty(context):
    context.result = context.runner.synthesize("   ", "qa-tts-empty")


@when("the voice runtime synthesizes a response text")
def step_synthesize_text(context):
    context.result = context.runner.synthesize("Bonjour", "qa-tts-fail")


@then("each reference text produces non-empty audio in the negotiated format")
def step_each_audio(context):
    for result in context.results:
        assert result.outcome is TtsOutcome.SUCCESS, result.outcome
        assert result.audio, "expected non-empty audio"
        assert result.audio_format == "pcm_16000", result.audio_format


@then("each synthesis emits a TTS first-audio span with its correlation id")
def step_each_span(context):
    spans = [s for s in context.telemetry.spans() if s.name == "voice.tts.first_audio"]
    assert len(spans) == len(context.results), (len(spans), len(context.results))
    correlations = {s.attributes["correlation_id"] for s in spans}
    assert correlations == {f"qa-tts-{i}" for i in range(len(context.results))}, correlations


@then("the TTS request latency is observable per turn")
def step_latency_observable(context):
    metrics = [m for m in context.telemetry.metrics() if m.name == "tts.request.duration_ms"]
    assert len(metrics) == len(context.results), (len(metrics), len(context.results))
    for result in context.results:
        assert result.tts_request_ms >= 0.0


@then("the synthesis outcome is reported unavailable")
def step_outcome_unavailable(context):
    assert context.result.outcome is TtsOutcome.UNAVAILABLE, context.result.outcome
    assert context.result.error_code == "empty_text", context.result.error_code


@then("no response audio is produced")
def step_no_audio_produced(context):
    assert context.result.audio == b"", context.result.audio


@then("no response audio is invented")
def step_no_audio_invented(context):
    assert context.result.outcome is TtsOutcome.FAILED, context.result.outcome
    assert context.result.audio == b""


@then("a stable TTS error code and sanitized reason are exposed")
def step_error_exposed(context):
    assert context.result.error_code == "tts_error", context.result.error_code
    assert context.result.error_reason, "expected a sanitized reason"


@then("the sanitized TTS reason contains no secret token")
def step_no_secret(context):
    reason = context.result.error_reason or ""
    assert SECRET_TOKEN not in reason, reason
    dump = " ".join(
        [str(e.attributes) for e in context.telemetry.events()]
        + [str(s.attributes) for s in context.telemetry.spans()]
        + [str(m.attributes) for m in context.telemetry.metrics()]
        + [lg.message + str(lg.attributes) for lg in context.telemetry.logs()]
    )
    assert SECRET_TOKEN not in dump, "secret token leaked into telemetry"
