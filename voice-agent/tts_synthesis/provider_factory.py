"""Select the TTS provider without changing the runner or QA harness (ST-3).

`fixture` (default) keeps the deterministic offline path; `gradium` builds the
real WebSocket provider from environment configuration. Provider choice is a
runtime decision so QA can run either without code changes. Mirror of
stt_validation/provider_factory.py.
"""

import os
from typing import Callable

from .gradium_tts_provider import (
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_VOICE_ID,
    GradiumTtsProvider,
)
from .providers import FixtureTtsProvider, TtsProvider
from .streaming import GradiumStreamingTtsProvider, StreamingTtsProvider

FIXTURE = "fixture"
GRADIUM = "gradium"
PROVIDER_NAMES = (FIXTURE, GRADIUM)

# Builds a streaming TTS provider for a given voice (TASK-WEB-023).
StreamingTtsBuilder = Callable[..., StreamingTtsProvider]

# The spike proved `voice_id=default` is rejected by Gradium ("Embeddings not
# found"). Treat the placeholder (and empty) as "unset" and fall back to the
# real FR Elise catalog voice so the live path works out of the box.
_PLACEHOLDER_VOICE_IDS = frozenset({"", "default"})


def build_provider(name: str = FIXTURE, *, voice_id: str | None = None) -> TtsProvider:
    if name == FIXTURE:
        return FixtureTtsProvider()
    if name == GRADIUM:
        return _build_gradium(voice_id)
    raise ValueError(f"Unknown TTS provider '{name}'; expected one of {PROVIDER_NAMES}")


def _build_gradium(voice_id: str | None = None) -> GradiumTtsProvider:
    api_key = os.environ.get("GRADIUM_API_KEY")
    if not api_key:
        raise ValueError("GRADIUM_API_KEY must be set to use the gradium provider")
    # US-042: Gradium selects the spoken language through the voice, not a language code, so a
    # per-session voice_id (from the UI selector) is how the TTS speaks the chosen language.
    return GradiumTtsProvider(
        api_key,
        voice_id=_resolve_voice_id(voice_id or os.environ.get("GRADIUM_VOICE_ID")),
        output_format=os.environ.get("GRADIUM_OUTPUT_FORMAT", DEFAULT_OUTPUT_FORMAT),
        model_name=os.environ.get("GRADIUM_MODEL_NAME", DEFAULT_MODEL),
    )


def _build_gradium_streaming(*, voice_id: str | None = None) -> StreamingTtsProvider:
    api_key = os.environ.get("GRADIUM_API_KEY")
    if not api_key:
        raise ValueError("GRADIUM_API_KEY must be set to use the gradium streaming provider")
    # US-042: a per-session voice_id (UI selector) is how the streaming TTS speaks the
    # chosen language (Gradium picks the language via the voice, not a language code).
    return GradiumStreamingTtsProvider(
        api_key,
        voice_id=_resolve_voice_id(voice_id or os.environ.get("GRADIUM_VOICE_ID")),
        output_format=os.environ.get("GRADIUM_OUTPUT_FORMAT", DEFAULT_OUTPUT_FORMAT),
        model_name=os.environ.get("GRADIUM_MODEL_NAME", DEFAULT_MODEL),
    )


# Registry of streaming TTS providers keyed by name (TASK-WEB-023): the mirror of the STT
# factory. Streaming selection goes through this registry, not a hard `== GRADIUM` branch,
# so a second vendor is a registration. The fixture provider stays batch-only (absent).
_STREAMING_TTS_BUILDERS: dict[str, StreamingTtsBuilder] = {GRADIUM: _build_gradium_streaming}


def register_streaming_provider(name: str, builder: StreamingTtsBuilder) -> None:
    """Register a streaming TTS provider builder under `name` (provider replaceability)."""
    _STREAMING_TTS_BUILDERS[name] = builder


def streaming_provider_names() -> tuple[str, ...]:
    """Names with a streaming TTS variant (drives provider-agnostic runtime selection)."""
    return tuple(_STREAMING_TTS_BUILDERS)


def supports_streaming(name: str) -> bool:
    """Whether `name` has a registered streaming TTS variant (batch fallback otherwise)."""
    return name in _STREAMING_TTS_BUILDERS


def build_streaming_provider(name: str = GRADIUM, *, voice_id: str | None = None) -> StreamingTtsProvider:
    """Build the streaming (WebSocket) TTS provider for incremental playback.

    Keyed on the provider registry (TASK-WEB-023): the runtime depends on the
    `StreamingTtsProvider` protocol, not on Gradium. Raises for a provider with no
    streaming variant; callers use `supports_streaming` to fall back to batch instead.
    """
    builder = _STREAMING_TTS_BUILDERS.get(name)
    if builder is None:
        raise ValueError(
            f"Streaming TTS is not available for provider '{name}'; "
            f"registered: {streaming_provider_names()}"
        )
    return builder(voice_id=voice_id)


def _resolve_voice_id(configured: str | None) -> str:
    if configured is None or configured.strip().lower() in _PLACEHOLDER_VOICE_IDS:
        return DEFAULT_VOICE_ID
    return configured.strip()
