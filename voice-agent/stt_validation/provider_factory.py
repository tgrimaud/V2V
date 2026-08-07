"""Select the STT provider without changing the validation harness (TASK-STT-008).

`fixture` (default) keeps the deterministic offline path; `gradium` builds the
real provider from environment configuration. Provider choice is a runtime
decision so QA can run either without code changes.
"""

import os
from typing import Callable

from .gradium_provider import (
    DEFAULT_INPUT_FORMAT,
    DEFAULT_LANGUAGE,
    GradiumSttProvider,
)
from .providers import FixtureSttProvider, SttProvider
from .streaming import GradiumStreamingSttProvider, StreamingSttProvider

FIXTURE = "fixture"
GRADIUM = "gradium"
PROVIDER_NAMES = (FIXTURE, GRADIUM)

# Builds a streaming STT provider for a given language (TASK-WEB-023).
StreamingSttBuilder = Callable[..., StreamingSttProvider]


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


def _build_gradium_streaming(*, language: str | None = None) -> StreamingSttProvider:
    api_key = os.environ.get("GRADIUM_API_KEY")
    if not api_key:
        raise ValueError("GRADIUM_API_KEY must be set to use the gradium streaming provider")
    # US-042: an explicit language (per-session UI selector) overrides the deployment
    # default so streaming STT listens in the language the customer picked.
    resolved = language or os.environ.get("GRADIUM_LANGUAGE", DEFAULT_LANGUAGE)
    return GradiumStreamingSttProvider(
        api_key,
        language=resolved,
        input_format=os.environ.get("GRADIUM_INPUT_FORMAT", DEFAULT_INPUT_FORMAT),
    )


# Registry of streaming STT providers keyed by name (TASK-WEB-023). Selecting the
# streaming provider goes through this registry instead of a hard-coded `== GRADIUM`
# check, so benchmarking a second vendor is a registration, not a branch edit. The
# fixture provider stays batch-only (absent here) -> the WebRTC path keeps its batch
# aggregator fallback for providers without a streaming variant.
_STREAMING_STT_BUILDERS: dict[str, StreamingSttBuilder] = {GRADIUM: _build_gradium_streaming}


def register_streaming_provider(name: str, builder: StreamingSttBuilder) -> None:
    """Register a streaming STT provider builder under `name` (provider replaceability)."""
    _STREAMING_STT_BUILDERS[name] = builder


def streaming_provider_names() -> tuple[str, ...]:
    """Names with a streaming STT variant (drives provider-agnostic runtime selection)."""
    return tuple(_STREAMING_STT_BUILDERS)


def supports_streaming(name: str) -> bool:
    """Whether `name` has a registered streaming STT variant (batch fallback otherwise)."""
    return name in _STREAMING_STT_BUILDERS


def build_streaming_provider(name: str = GRADIUM, *, language: str | None = None) -> StreamingSttProvider:
    """Build the streaming (WebSocket) STT provider for the low-latency voice path.

    Keyed on the provider registry (TASK-WEB-023): the runtime depends on the
    `StreamingSttProvider` protocol, not on Gradium. Raises for a provider with no
    streaming variant; callers use `supports_streaming` to fall back to batch instead.
    """
    builder = _STREAMING_STT_BUILDERS.get(name)
    if builder is None:
        raise ValueError(
            f"Streaming STT is not available for provider '{name}'; "
            f"registered: {streaming_provider_names()}"
        )
    return builder(language=language)
