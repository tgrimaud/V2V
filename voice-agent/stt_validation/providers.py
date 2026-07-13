from pathlib import Path
from typing import Protocol


class NoSpeechDetectedError(RuntimeError):
    """The provider processed the audio but found no usable speech.

    Raised (instead of a generic error) so the runner can report the outcome as
    UNAVAILABLE rather than FAILED. Provider-agnostic on purpose: any adapter can
    signal "no usable speech" without the runner string-matching messages.
    """


class SttProvider(Protocol):
    @property
    def name(self) -> str:
        ...

    def transcribe(self, audio_path: Path) -> str:
        ...


class FixtureSttProvider:
    """Deterministic provider for QA fixtures; real STT adapters can replace it."""

    name = "fixture-stt"

    def transcribe(self, audio_path: Path) -> str:
        transcript_path = audio_path.with_suffix(".txt")
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio fixture not found: {audio_path}")
        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript fixture not found: {transcript_path}")
        transcript = transcript_path.read_text(encoding="utf-8").strip()
        if not transcript:
            raise NoSpeechDetectedError("Transcript fixture contains no usable speech")
        return transcript
