"""STT validation scaffold for controlled audio fixtures."""

from .gradium_provider import GradiumResponse, GradiumSttError, GradiumSttProvider
from .models import SttOutcome, TranscriptResult
from .pipeline_timing import (
    PIPELINE_SLICES,
    PipelineTimingReport,
    SliceTiming,
)
from .provider_factory import (
    PROVIDER_NAMES,
    build_provider,
    build_streaming_provider,
    register_streaming_provider,
    streaming_provider_names,
    supports_streaming,
)
from .providers import FixtureSttProvider, NoSpeechDetectedError, SttProvider
from .quality import (
    MIN_SAMPLES_FOR_PERCENTILES,
    CategorySummary,
    FixtureAssessment,
    FixtureCategory,
    FixtureQualityReport,
    FixtureSpec,
    evaluate_fixture_set,
    normalize_transcript,
    word_error_rate,
)
from .runner import SttValidationRunner
from .streaming import (
    FinalTranscript,
    GradiumStreamingSession,
    GradiumStreamingSttProvider,
    PartialTranscript,
    StreamingSttError,
    StreamingSttProvider,
    StreamingSttSession,
)
from .telemetry import LatencyReport, TelemetryRecorder

__all__ = [
    "MIN_SAMPLES_FOR_PERCENTILES",
    "PROVIDER_NAMES",
    "CategorySummary",
    "FixtureAssessment",
    "FixtureCategory",
    "FixtureQualityReport",
    "FixtureSpec",
    "FinalTranscript",
    "FixtureSttProvider",
    "GradiumResponse",
    "GradiumStreamingSession",
    "GradiumStreamingSttProvider",
    "GradiumSttError",
    "GradiumSttProvider",
    "LatencyReport",
    "NoSpeechDetectedError",
    "PartialTranscript",
    "StreamingSttError",
    "StreamingSttProvider",
    "StreamingSttSession",
    "build_streaming_provider",
    "register_streaming_provider",
    "streaming_provider_names",
    "supports_streaming",
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
    "normalize_transcript",
    "word_error_rate",
]
