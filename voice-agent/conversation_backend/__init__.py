"""Conversation backend seam (US-019 middle, TASK-WEB-003).

The neutral middle of the Voice2Voice loop: it takes an STT transcript and returns
a response text for the TTS half. It defines the conversation contract
(AnswerRequest / AnswerResult) and the BackendAnswerPort protocol; concrete
adapters (stub, HTTP) are added by later sub-tickets.

This package MUST NOT import stt_validation, tts_synthesis or web_voice. It may
import the neutral voice_common package. Enforced by
tests/test_architecture_separation.py.
"""

from .backend_factory import BACKEND_NAMES, HTTP, STUB, build_backend
from .degraded import (
    BACKEND_UNAVAILABLE_REASON,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEGRADED_FALLBACK_TEXT,
    EMPTY_ANSWER_REASON,
    LOW_CONFIDENCE_REASON,
    degraded_answer,
)
from .http_backend import HttpBackendAdapter, HttpBackendError, HttpResponse
from .models import AnswerOutcome, AnswerRequest, AnswerResult, ConversationEnvelope
from .port import BackendAnswerPort, EmptyTranscriptError
from .stub_backend import STUB_ANSWER_TEXT, StubBackendAdapter

__all__ = [
    "AnswerOutcome",
    "AnswerRequest",
    "AnswerResult",
    "BACKEND_NAMES",
    "BACKEND_UNAVAILABLE_REASON",
    "BackendAnswerPort",
    "ConversationEnvelope",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DEGRADED_FALLBACK_TEXT",
    "EMPTY_ANSWER_REASON",
    "EmptyTranscriptError",
    "HTTP",
    "HttpBackendAdapter",
    "HttpBackendError",
    "HttpResponse",
    "LOW_CONFIDENCE_REASON",
    "STUB",
    "STUB_ANSWER_TEXT",
    "StubBackendAdapter",
    "build_backend",
    "degraded_answer",
]
