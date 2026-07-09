from pathlib import Path
from tempfile import TemporaryDirectory

from behave import given, then, when

from stt_validation import (
    FixtureSttProvider,
    SttOutcome,
    SttValidationRunner,
    TelemetryRecorder,
    evaluate_fixture_set,
)
from stt_validation.manifest import load_manifest

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = VOICE_AGENT_ROOT / "fixtures" / "manifest.json"


def _runner() -> SttValidationRunner:
    return SttValidationRunner(FixtureSttProvider(), TelemetryRecorder())


def _usable(context):
    return [a for a in context.report.assessments if a.expect_usable]


def _by_category(context, category: str):
    return next(a for a in context.report.assessments if a.category == category)


@given("the QA STT fixture manifest")
def step_load_manifest(context):
    assert MANIFEST_PATH.exists(), f"manifest not found: {MANIFEST_PATH}"
    context.manifest = load_manifest(MANIFEST_PATH)


@when("QA runs the STT validation harness over the fixture set")
def step_run_harness(context):
    manifest = context.manifest
    context.report = evaluate_fixture_set(
        _runner(),
        manifest.specs,
        manifest.expected_categories,
        manifest.quality_threshold,
    )


@then("every usable fixture category is scored against its reference transcript")
def step_usable_scored(context):
    usable = _usable(context)
    assert usable, "expected at least one usable fixture"
    for assessment in usable:
        assert assessment.reference is not None, f"{assessment.name} has no reference"
        assert assessment.quality_score is not None, f"{assessment.name} was not scored"


@then("every usable fixture meets the configured quality threshold")
def step_usable_threshold(context):
    threshold = context.report.quality_threshold
    for assessment in _usable(context):
        assert assessment.quality_ok, (
            f"{assessment.name} below threshold: "
            f"{assessment.quality_score} < {threshold}"
        )


@then("the silence fixture is reported as failed or unavailable")
def step_silence_failed(context):
    silence = _by_category(context, "silence")
    assert silence.outcome in {SttOutcome.FAILED.value, "unavailable"}, silence.outcome


@then("the silence fixture transcript is empty")
def step_silence_empty(context):
    silence = _by_category(context, "silence")
    assert silence.transcript.strip() == "", "silence must not invent a transcript"


@then("no declared fixture category is missing")
def step_no_missing(context):
    assert context.report.missing_categories == [], context.report.missing_categories


@then("the overall fixture set is reported as ready")
def step_ready(context):
    assert context.report.ready, "fixture set is not ready"


@then("a latency distribution with p50, p95 and p99 is available")
def step_latency_distribution(context):
    latency = context.report.latency.to_dict()
    for key in ("count", "p50_ms", "p95_ms", "p99_ms"):
        assert key in latency, f"missing {key} in latency report"
    assert latency["count"] == len(context.report.assessments)


@then("each fixture reports its isolated STT slice duration")
def step_per_fixture_latency(context):
    for assessment in context.report.assessments:
        assert assessment.stt_request_ms >= 0.0, assessment.name


@given("an audio fixture whose transcript sidecar is missing")
def step_missing_sidecar(context):
    context._tmp = TemporaryDirectory()
    audio = Path(context._tmp.name) / "orphan-clip.wav"
    audio.write_bytes(b"\x00\x00")
    context.orphan_audio = audio


@when("QA runs the STT validation path on that fixture")
def step_run_failure(context):
    context.failure_result = _runner().validate(context.orphan_audio, "qa-failure-run")


@then("the outcome is failed")
def step_outcome_failed(context):
    assert context.failure_result.outcome is SttOutcome.FAILED


@then("a correlation id is recorded for the run")
def step_correlation_id(context):
    assert context.failure_result.correlation_id == "qa-failure-run"


@then("the sanitized failure reason contains no filesystem path")
def step_sanitized_reason(context):
    reason = context.failure_result.error_reason or ""
    assert "/" not in reason and "\\" not in reason, reason
    assert context.failure_result.error_code, "expected a stable error code"
    if hasattr(context, "_tmp"):
        context._tmp.cleanup()
