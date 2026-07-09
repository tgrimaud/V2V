"""STT validation scaffold for controlled audio fixtures."""

from .models import SttOutcome, TranscriptResult
from .providers import FixtureSttProvider
from .runner import SttValidationRunner
from .telemetry import LatencyReport, TelemetryRecorder

__all__ = [
    "FixtureSttProvider",
    "LatencyReport",
    "SttOutcome",
    "SttValidationRunner",
    "TelemetryRecorder",
    "TranscriptResult",
]
