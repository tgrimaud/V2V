"""TTS synthesis scaffold (voice-out), the symmetric mirror of stt_validation.

This package MUST NOT import from stt_validation (and vice versa). The only shared
code is stateless cross-cutting utilities (telemetry, sanitization). Enforced by
tests/test_architecture_separation.py.
"""

from .gradium_tts_provider import (
    DEFAULT_VOICE_ID,
    GRADIUM_TTS_URL,
    GradiumTtsError,
    GradiumTtsProvider,
)
from .models import SynthesisResult, TtsOutcome
from .provider_factory import PROVIDER_NAMES, build_provider
from .providers import (
    DEFAULT_AUDIO_FORMAT,
    EmptyTextError,
    FixtureTtsProvider,
    TtsProvider,
)
from .runner import EMPTY_TEXT_CODE, TTS_FIRST_AUDIO_SPAN, TtsSynthesisRunner

__all__ = [
    "DEFAULT_AUDIO_FORMAT",
    "DEFAULT_VOICE_ID",
    "EMPTY_TEXT_CODE",
    "GRADIUM_TTS_URL",
    "GradiumTtsError",
    "GradiumTtsProvider",
    "PROVIDER_NAMES",
    "TTS_FIRST_AUDIO_SPAN",
    "EmptyTextError",
    "FixtureTtsProvider",
    "SynthesisResult",
    "TtsOutcome",
    "TtsProvider",
    "TtsSynthesisRunner",
    "build_provider",
]
