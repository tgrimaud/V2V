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
    """Accumulates all audio, transcribes once via Gradium REST on finalize."""

    def __init__(self, language: str, api_key: str, input_format: str = "pcm_16000"):
        self._buffer = bytearray()
        self._language = language
        self._api_key = api_key
        self._input_format = input_format

    def feed(self, pcm: bytes) -> None:
        self._buffer.extend(pcm)

    async def finalize(self) -> SttResult:
        if not self._buffer:
            return SttResult(text=None)
        return await transcribe_audio(
            bytes(self._buffer), self._language, self._api_key, self._input_format
        )


def create_stt_session(
    language: str, api_key: str, input_format: str = "pcm_16000"
) -> StreamingSttSession:
    """Factory for the active STT engine. Returns the batch engine for now.

    `input_format` selects the audio encoding: `pcm_16000` for web/PCM clients,
    `ulaw_8000` for telephony.
    """
    return BatchSttSession(language, api_key, input_format)
