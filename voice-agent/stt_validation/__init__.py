"""STT validation scaffold for controlled audio fixtures."""

from .gradium_provider import GradiumResponse, GradiumSttError, GradiumSttProvider
from .models import SttOutcome, TranscriptResult
from .pipeline_timing import (
    PIPELINE_SLICES,
    PipelineTimingReport,
    SliceTiming,
)
from .provider_factory import PROVIDER_NAMES, build_provider
from .providers import FixtureSttProvider, SttProvider
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
    "PROVIDER_NAMES",
    "FixtureAssessment",
    "FixtureCategory",
    "FixtureQualityReport",
    "FixtureSpec",
    "FixtureSttProvider",
    "GradiumResponse",
    "GradiumSttError",
    "GradiumSttProvider",
    "LatencyReport",
    "PIPELINE_SLICES",
    "PipelineTimingReport",
    "SliceTiming",
    "SttOutcome",
    "SttProvider",
    "SttValidationRunner",
    "TelemetryRecorder",
    "TranscriptResult",
    "build_provider",
    "evaluate_fixture_set",
    "word_error_rate",
]
