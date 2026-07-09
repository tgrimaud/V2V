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

FIXTURE = "fixture"
GRADIUM = "gradium"
PROVIDER_NAMES = (FIXTURE, GRADIUM)


def build_provider(name: str = FIXTURE) -> SttProvider:
    if name == FIXTURE:
        return FixtureSttProvider()
    if name == GRADIUM:
        return _build_gradium()
    raise ValueError(f"Unknown STT provider '{name}'; expected one of {PROVIDER_NAMES}")


def _build_gradium() -> GradiumSttProvider:
    api_key = os.environ.get("GRADIUM_API_KEY")
    if not api_key:
        raise ValueError("GRADIUM_API_KEY must be set to use the gradium provider")
    return GradiumSttProvider(
        api_key,
        language=os.environ.get("GRADIUM_LANGUAGE", DEFAULT_LANGUAGE),
        input_format=os.environ.get("GRADIUM_INPUT_FORMAT", DEFAULT_INPUT_FORMAT),
    )
