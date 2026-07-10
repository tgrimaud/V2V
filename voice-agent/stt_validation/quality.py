import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .models import SttOutcome
from .runner import SttValidationRunner
from .telemetry import LatencyReport

DEFAULT_QUALITY_THRESHOLD = 0.8

# Minimum samples in a category before its latency percentiles / quality are
# reported as statistically meaningful. Below this a single outlier dominates
# p95/p99, so the category is flagged "not yet significant". This is a pragmatic
# reporting floor; stable p95/p99 realistically needs many more (and, for noisy /
# accented, real human recordings — see TASK-STT-007 open risks).
MIN_SAMPLES_FOR_PERCENTILES = 5

# Anything that is neither a word character nor whitespace (punctuation, symbols).
_PUNCTUATION = re.compile(r"[^\w\s]", flags=re.UNICODE)


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
class CategorySummary:
    category: str
    sample_count: int
    usable_count: int
    passed_count: int
    mean_wer: float | None
    worst_wer: float | None
    latency: LatencyReport
    significant: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "sample_count": self.sample_count,
            "usable_count": self.usable_count,
            "passed_count": self.passed_count,
            "mean_wer": self.mean_wer,
            "worst_wer": self.worst_wer,
            "significant": self.significant,
            "latency_report": self.latency.to_dict(),
        }


@dataclass(frozen=True)
class FixtureQualityReport:
    assessments: list[FixtureAssessment]
    missing_categories: list[str]
    quality_threshold: float
    latency: LatencyReport
    category_summaries: list[CategorySummary]
    min_samples_for_percentiles: int = MIN_SAMPLES_FOR_PERCENTILES

    @property
    def ready(self) -> bool:
        return not self.missing_categories and all(a.quality_ok for a in self.assessments)

    @property
    def all_categories_significant(self) -> bool:
        # Significance only applies to categories with usable (scored) fixtures;
        # unusable categories (e.g. silence) carry no WER and are excluded.
        scored = [c for c in self.category_summaries if c.usable_count > 0]
        return bool(scored) and all(c.significant for c in scored)

    def failed_categories(self) -> list[str]:
        return sorted({a.category for a in self.assessments if not a.quality_ok})

    def underpowered_categories(self) -> list[str]:
        return sorted(
            c.category
            for c in self.category_summaries
            if c.usable_count > 0 and not c.significant
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "all_categories_significant": self.all_categories_significant,
            "quality_threshold": self.quality_threshold,
            "min_samples_for_percentiles": self.min_samples_for_percentiles,
            "missing_categories": self.missing_categories,
            "failed_categories": self.failed_categories(),
            "underpowered_categories": self.underpowered_categories(),
            "latency_report": self.latency.to_dict(),
            "category_summaries": [summary.to_dict() for summary in self.category_summaries],
            "assessments": [assessment.to_dict() for assessment in self.assessments],
        }


def normalize_transcript(text: str) -> str:
    """Fold case, accents and punctuation so formatting-only diffs are not errors.

    Applied identically to reference and hypothesis before WER so that a real STT
    engine is not penalized for capitalization (`Est-ce` vs `est-ce`), punctuation
    (`Bonjour` vs `Bonjour.`) or accents (`telephone` vs `téléphone`).
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    stripped = _PUNCTUATION.sub(" ", without_accents.lower())
    return " ".join(stripped.split())


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein word error rate on normalized text; 0.0 means a semantic match.

    Both sides are normalized (see `normalize_transcript`) so case, punctuation and
    accent differences score 0.0 while genuine substitutions/omissions still count.
    """
    ref_words = normalize_transcript(reference).split()
    hyp_words = normalize_transcript(hypothesis).split()
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
    summaries = _summarize_categories(assessments)
    return FixtureQualityReport(assessments, sorted(missing), quality_threshold, latency, summaries)


def _summarize_categories(assessments: list[FixtureAssessment]) -> list[CategorySummary]:
    grouped: dict[str, list[FixtureAssessment]] = {}
    for assessment in assessments:
        grouped.setdefault(assessment.category, []).append(assessment)
    return [_summarize_one(category, grouped[category]) for category in sorted(grouped)]


def _summarize_one(category: str, items: list[FixtureAssessment]) -> CategorySummary:
    wers = [a.wer for a in items if a.wer is not None]
    return CategorySummary(
        category=category,
        sample_count=len(items),
        usable_count=sum(1 for a in items if a.expect_usable),
        passed_count=sum(1 for a in items if a.quality_ok),
        mean_wer=round(sum(wers) / len(wers), 3) if wers else None,
        worst_wer=round(max(wers), 3) if wers else None,
        latency=LatencyReport.from_samples([a.stt_request_ms for a in items]),
        significant=len(items) >= MIN_SAMPLES_FOR_PERCENTILES,
    )


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
