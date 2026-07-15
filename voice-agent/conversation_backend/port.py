from typing import Protocol

from .models import AnswerRequest, AnswerResult


class EmptyTranscriptError(RuntimeError):
    """The backend was asked to answer an empty / whitespace-only transcript.

    Raised (instead of a generic error) so the caller can report the outcome as
    UNAVAILABLE rather than DEGRADED or FAILED. Provider-agnostic on purpose: any
    adapter can signal "nothing to answer" without the caller string-matching
    messages. Mirror of EmptyTextError (TTS) / NoSpeechDetectedError (STT).
    """


class BackendAnswerPort(Protocol):
    @property
    def name(self) -> str:
        ...

    def answer(self, request: AnswerRequest) -> AnswerResult:
        ...
