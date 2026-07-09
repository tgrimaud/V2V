from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .models import SttOutcome
from .runner import SttValidationRunner
from .telemetry import LatencyReport

DEFAULT_QUALITY_THRESHOLD = 0.8


class FixtureCategory(str, Enum):
    SHORT = "short"
    LONG = "long"
    NOISY = "noisy"
    SILENCE = "silence"
    ACCENTED = "accented"


@dataclass(frozen=True)
class FixtureSpec:
    name: str
    category: FixtureCategory
    audio_path: Path
    reference: str | None
    expect_usable: bool


@dataclass(frozen=True)
class FixtureAssessment:
    name: str
    category: str
    outcome: str
    transcript: str
    reference: str | None
    wer: float | None
    quality_score: float | None
    expect_usable: bool
    quality_ok: bool
    note: str
    error_code: str | None
    error_reason: str | None
    stt_request_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "outcome": self.outcome,
            "transcript": self.transcript,
            "reference": self.reference,
            "wer": self.wer,
            "quality_score": self.quality_score,
            "expect_usable": self.expect_usable,
            "quality_ok": self.quality_ok,
            "note": self.note,
            "error_code": self.error_code,
            "error_reason": self.error_reason,
            "stt_request_ms": round(self.stt_request_ms, 3),
        }


@dataclass(frozen=True)
class FixtureQualityReport:
    assessments: list[FixtureAssessment]
    missing_categories: list[str]
    quality_threshold: float
    latency: LatencyReport

    @property
    def ready(self) -> bool:
        return not self.missing_categories and all(a.quality_ok for a in self.assessments)

    def failed_categories(self) -> list[str]:
        return sorted({a.category for a in self.assessments if not a.quality_ok})

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "quality_threshold": self.quality_threshold,
            "missing_categories": self.missing_categories,
            "failed_categories": self.failed_categories(),
            "latency_report": self.latency.to_dict(),
            "assessments": [assessment.to_dict() for assessment in self.assessments],
        }


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein word error rate; 0.0 means the hypothesis matches exactly."""
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    distance = _edit_distance(ref_words, hyp_words)
    return distance / len(ref_words)


def _edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, ref_word in enumerate(reference, start=1):
        current = [i]
        for j, hyp_word in enumerate(hypothesis, start=1):
            substitution = previous[j - 1] + (0 if ref_word == hyp_word else 1)
            current.append(min(substitution, previous[j] + 1, current[j - 1] + 1))
        previous = current
    return previous[-1]


def evaluate_fixture_set(
    runner: SttValidationRunner,
    specs: list[FixtureSpec],
    expected_categories: list[FixtureCategory],
    quality_threshold: float = DEFAULT_QUALITY_THRESHOLD,
) -> FixtureQualityReport:
    assessments = [_assess(runner, spec, quality_threshold) for spec in specs]
    covered = {spec.category for spec in specs}
    missing = [category.value for category in expected_categories if category not in covered]
    latency = LatencyReport.from_samples([a.stt_request_ms for a in assessments])
    return FixtureQualityReport(assessments, sorted(missing), quality_threshold, latency)


def _assess(runner: SttValidationRunner, spec: FixtureSpec, threshold: float) -> FixtureAssessment:
    result = runner.validate(spec.audio_path, spec.name)
    succeeded = result.outcome is SttOutcome.SUCCESS
    if not spec.expect_usable:
        return _assess_unusable(spec, result, succeeded)
    return _assess_usable(spec, result, succeeded, threshold)


def _assess_usable(spec, result, succeeded, threshold) -> FixtureAssessment:  # type: ignore[no-untyped-def]
    wer = None
    quality_score = None
    if succeeded and spec.reference is not None:
        wer = round(word_error_rate(spec.reference, result.transcript), 3)
        quality_score = round(max(0.0, 1.0 - wer), 3)
    quality_ok = bool(succeeded and quality_score is not None and quality_score >= threshold)
    note = _usable_note(succeeded, quality_score, threshold)
    return _build_assessment(spec, result, wer, quality_score, quality_ok, note)


def _assess_unusable(spec, result, succeeded) -> FixtureAssessment:  # type: ignore[no-untyped-def]
    invented = succeeded and bool(result.transcript.strip())
    quality_ok = not invented
    note = (
        "invented transcript for unusable audio"
        if invented
        else "correctly reported as unusable, no transcript invented"
    )
    return _build_assessment(spec, result, None, None, quality_ok, note)


def _usable_note(succeeded: bool, quality_score: float | None, threshold: float) -> str:
    if not succeeded:
        return "STT failed to produce a transcript"
    if quality_score is None:
        return "no reference transcript to score against"
    if quality_score >= threshold:
        return "transcript quality meets threshold"
    return "transcript quality below threshold"


def _build_assessment(spec, result, wer, quality_score, quality_ok, note) -> FixtureAssessment:  # type: ignore[no-untyped-def]
    return FixtureAssessment(
        name=spec.name,
        category=spec.category.value,
        outcome=result.outcome.value,
        transcript=result.transcript,
        reference=spec.reference,
        wer=wer,
        quality_score=quality_score,
        expect_usable=spec.expect_usable,
        quality_ok=quality_ok,
        note=note,
        error_code=result.error_code,
        error_reason=result.error_reason,
        stt_request_ms=result.stt_request_ms,
    )
