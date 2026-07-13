"""Domain-neutral cross-cutting utilities shared by both voice halves.

`stt_validation` (voice-in) and `tts_synthesis` (voice-out) both depend on this
package, but never on each other. Only stateless, domain-agnostic helpers live
here: telemetry recording/latency reporting and error sanitization.
"""

from .sanitization import SanitizedError, sanitize_error
from .telemetry import (
    LatencyReport,
    MetricSample,
    Span,
    StructuredLog,
    TelemetryEvent,
    TelemetryRecorder,
    Timer,
)

__all__ = [
    "LatencyReport",
    "MetricSample",
    "SanitizedError",
    "Span",
    "StructuredLog",
    "TelemetryEvent",
    "TelemetryRecorder",
    "Timer",
    "sanitize_error",
]
