"""Select the TTS provider without changing the runner or QA harness (ST-3).

`fixture` (default) keeps the deterministic offline path; `gradium` builds the
real WebSocket provider from environment configuration. Provider choice is a
runtime decision so QA can run either without code changes. Mirror of
stt_validation/provider_factory.py.
"""

import os

from .gradium_tts_provider import (
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_VOICE_ID,
    GradiumTtsProvider,
)
from .providers import FixtureTtsProvider, TtsProvider
from .streaming import GradiumStreamingTtsProvider

FIXTURE = "fixture"
GRADIUM = "gradium"
PROVIDER_NAMES = (FIXTURE, GRADIUM)

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


def build_streaming_provider(name: str = GRADIUM) -> GradiumStreamingTtsProvider:
    """Build the streaming (WebSocket) TTS provider for incremental playback.

    Only Gradium has a streaming variant (TASK-WEB-004); the fixture provider stays
    batch-only, so the WebRTC path falls back to the batch TTS processor when the
    streaming provider is not available.
    """
    if name != GRADIUM:
        raise ValueError(f"Streaming TTS is only available for the '{GRADIUM}' provider")
    api_key = os.environ.get("GRADIUM_API_KEY")
    if not api_key:
        raise ValueError("GRADIUM_API_KEY must be set to use the gradium streaming provider")
    return GradiumStreamingTtsProvider(
        api_key,
        voice_id=_resolve_voice_id(os.environ.get("GRADIUM_VOICE_ID")),
        output_format=os.environ.get("GRADIUM_OUTPUT_FORMAT", DEFAULT_OUTPUT_FORMAT),
        model_name=os.environ.get("GRADIUM_MODEL_NAME", DEFAULT_MODEL),
    )


def _resolve_voice_id(configured: str | None) -> str:
    if configured is None or configured.strip().lower() in _PLACEHOLDER_VOICE_IDS:
        return DEFAULT_VOICE_ID
    return configured.strip()
