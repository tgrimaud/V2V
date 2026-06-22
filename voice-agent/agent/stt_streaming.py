"""Streaming STT abstraction.

Decouples the bridge from a specific STT engine. A session is fed PCM frames
incrementally and produces a final transcription on finalize().

The current concrete implementation (BatchSttSession) accumulates audio and
calls the Gradium REST endpoint once on finalize -- this preserves today's
behaviour behind a streaming-shaped seam. A future GradiumWebSocketSttSession
or WhisperStreamingSttSession can implement the same Protocol to emit partial
transcripts and cut the STT tail latency, without touching the bridge.
"""

from typing import Protocol, runtime_checkable

from agent.gradium_stt import SttResult, transcribe_audio


@runtime_checkable
class StreamingSttSession(Protocol):
    """A single utterance's STT session, fed PCM incrementally."""

    def feed(self, pcm: bytes) -> None:
        """Append PCM 16-bit mono audio to the session."""

    async def finalize(self) -> SttResult:
        """Finish the utterance and return the transcription result."""


class BatchSttSession:
    """Accumulates all PCM, transcribes once via Gradium REST on finalize."""

    def __init__(self, language: str, api_key: str):
        self._buffer = bytearray()
        self._language = language
        self._api_key = api_key

    def feed(self, pcm: bytes) -> None:
        self._buffer.extend(pcm)

    async def finalize(self) -> SttResult:
        if not self._buffer:
            return SttResult(text=None)
        return await transcribe_audio(bytes(self._buffer), self._language, self._api_key)


def create_stt_session(language: str, api_key: str) -> StreamingSttSession:
    """Factory for the active STT engine. Returns the batch engine for now."""
    return BatchSttSession(language, api_key)
