"""STT-facing view of the shared voice-journey timing aggregator.

The implementation now lives in the domain-neutral `voice_common` package so both
halves can build the same per-slice report without importing `stt_validation`.
This module re-exports it to keep the existing `stt_validation.pipeline_timing`
import surface (CLI, tests, behave steps) stable.
"""

from voice_common.pipeline_timing import (
    BACKEND_FIRST_TOKEN,
    CHANNEL_EGRESS,
    CHANNEL_INGRESS,
    END_OF_TURN,
    PIPELINE_SLICES,
    STT,
    TTS_FIRST_AUDIO,
    PipelineTimingReport,
    SliceTiming,
)

__all__ = [
    "BACKEND_FIRST_TOKEN",
    "CHANNEL_EGRESS",
    "CHANNEL_INGRESS",
    "END_OF_TURN",
    "PIPELINE_SLICES",
    "STT",
    "TTS_FIRST_AUDIO",
    "PipelineTimingReport",
    "SliceTiming",
]
