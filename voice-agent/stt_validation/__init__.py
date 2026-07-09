"""STT validation scaffold for controlled audio fixtures."""

from .models import SttOutcome, TranscriptResult
from .providers import FixtureSttProvider
from .quality import (
    FixtureAssessment,
    FixtureCategory,
    FixtureQualityReport,
    FixtureSpec,
    evaluate_fixture_set,
    word_error_rate,
)
from .runner import SttValidationRunner
from .telemetry import LatencyReport, TelemetryRecorder

__all__ = [
    "FixtureAssessment",
    "FixtureCategory",
    "FixtureQualityReport",
    "FixtureSpec",
    "FixtureSttProvider",
    "LatencyReport",
    "SttOutcome",
    "SttValidationRunner",
    "TelemetryRecorder",
    "TranscriptResult",
    "evaluate_fixture_set",
    "word_error_rate",
]
