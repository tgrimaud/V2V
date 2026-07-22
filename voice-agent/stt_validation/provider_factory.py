"""Select the STT provider without changing the validation harness (TASK-STT-008).

`fixture` (default) keeps the deterministic offline path; `gradium` builds the
real provider from environment configuration. Provider choice is a runtime
decision so QA can run either without code changes.
"""

import os

from .gradium_provider import (
    DEFAULT_INPUT_FORMAT,
    DEFAULT_LANGUAGE,
    GradiumSttProvider,
)
from .providers import FixtureSttProvider, SttProvider
from .streaming import GradiumStreamingSttProvider

FIXTURE = "fixture"
GRADIUM = "gradium"
PROVIDER_NAMES = (FIXTURE, GRADIUM)


def build_provider(name: str = FIXTURE, *, language: str | None = None) -> SttProvider:
    if name == FIXTURE:
        return FixtureSttProvider()
    if name == GRADIUM:
        return _build_gradium(language)
    raise ValueError(f"Unknown STT provider '{name}'; expected one of {PROVIDER_NAMES}")


def _build_gradium(language: str | None = None) -> GradiumSttProvider:
    api_key = os.environ.get("GRADIUM_API_KEY")
    if not api_key:
        raise ValueError("GRADIUM_API_KEY must be set to use the gradium provider")
    # US-042: an explicit language (from the per-session UI selector) overrides the deployment
    # default so the transcription listens in the language the customer picked.
    resolved = language or os.environ.get("GRADIUM_LANGUAGE", DEFAULT_LANGUAGE)
    return GradiumSttProvider(
        api_key,
        language=resolved,
        input_format=os.environ.get("GRADIUM_INPUT_FORMAT", DEFAULT_INPUT_FORMAT),
    )


def build_streaming_provider(name: str = GRADIUM, *, language: str | None = None) -> GradiumStreamingSttProvider:
    """Build the streaming (WebSocket) STT provider for the low-latency voice path.

    Only Gradium has a streaming variant (TASK-STT-010); the fixture provider stays
    batch-only, so the WebRTC path falls back to the batch aggregator when the
    streaming provider is not available. US-042: an explicit language (per-session UI
    selector) overrides the deployment default so streaming STT listens in it.
    """
    if name != GRADIUM:
        raise ValueError(f"Streaming STT is only available for the '{GRADIUM}' provider")
    api_key = os.environ.get("GRADIUM_API_KEY")
    if not api_key:
        raise ValueError("GRADIUM_API_KEY must be set to use the gradium streaming provider")
    resolved = language or os.environ.get("GRADIUM_LANGUAGE", DEFAULT_LANGUAGE)
    return GradiumStreamingSttProvider(
        api_key,
        language=resolved,
        input_format=os.environ.get("GRADIUM_INPUT_FORMAT", DEFAULT_INPUT_FORMAT),
    )
