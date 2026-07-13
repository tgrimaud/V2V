"""STT-facing view of the shared telemetry recorder.

The implementation now lives in the domain-neutral `voice_common` package so the
TTS half can reuse it without importing `stt_validation`. This module re-exports
it to keep the existing `stt_validation.telemetry` import surface stable.
"""

from voice_common.telemetry import (
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
    "Span",
    "StructuredLog",
    "TelemetryEvent",
    "TelemetryRecorder",
    "Timer",
]
