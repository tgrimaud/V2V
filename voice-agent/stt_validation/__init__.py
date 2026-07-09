"""STT validation scaffold for controlled audio fixtures."""

from .models import SttOutcome, TranscriptResult
from .providers import FixtureSttProvider
from .runner import SttValidationRunner

__all__ = [
    "FixtureSttProvider",
    "SttOutcome",
    "SttValidationRunner",
    "TranscriptResult",
]
