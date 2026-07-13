"""TTS synthesis scaffold (voice-out), the symmetric mirror of stt_validation.

This package MUST NOT import from stt_validation (and vice versa). The only shared
code is stateless cross-cutting utilities (telemetry, sanitization). Enforced by
tests/test_architecture_separation.py.
"""

from .models import SynthesisResult, TtsOutcome
from .providers import (
    DEFAULT_AUDIO_FORMAT,
    EmptyTextError,
    FixtureTtsProvider,
    TtsProvider,
)

__all__ = [
    "DEFAULT_AUDIO_FORMAT",
    "EmptyTextError",
    "FixtureTtsProvider",
    "SynthesisResult",
    "TtsOutcome",
    "TtsProvider",
]
