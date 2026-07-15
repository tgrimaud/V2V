"""Conversation backend seam (US-019 middle, TASK-WEB-003).

The neutral middle of the Voice2Voice loop: it takes an STT transcript and returns
a response text for the TTS half. It defines the conversation contract
(AnswerRequest / AnswerResult) and the BackendAnswerPort protocol; concrete
adapters (stub, HTTP) are added by later sub-tickets.

This package MUST NOT import stt_validation, tts_synthesis or web_voice. It may
import the neutral voice_common package. Enforced by
tests/test_architecture_separation.py.
"""

from .models import AnswerOutcome, AnswerRequest, AnswerResult, ConversationEnvelope
from .port import BackendAnswerPort, EmptyTranscriptError

__all__ = [
    "AnswerOutcome",
    "AnswerRequest",
    "AnswerResult",
    "BackendAnswerPort",
    "ConversationEnvelope",
    "EmptyTranscriptError",
]
