import array
import math
from typing import Protocol

DEFAULT_SAMPLE_RATE_HZ = 16000
DEFAULT_AUDIO_FORMAT = "pcm_16000"


class EmptyTextError(RuntimeError):
    """The provider was asked to synthesize empty / whitespace-only text.

    Raised (instead of a generic error) so the runner can report the outcome as
    UNAVAILABLE rather than FAILED. Provider-agnostic on purpose: any adapter can
    signal "nothing to speak" without the runner string-matching messages. Mirror
    of NoSpeechDetectedError on the STT side.
    """


class TtsProvider(Protocol):
    @property
    def name(self) -> str:
        ...

    def synthesize(self, text: str) -> bytes:
        ...


class FixtureTtsProvider:
    """Deterministic provider for offline QA; real TTS adapters can replace it.

    Produces a synthetic PCM16 mono tone whose duration scales with the text
    length, so tests can assert audio was produced (non-empty, right format,
    plausible duration) without any network call or committed binary fixture.
    """

    name = "fixture-tts"

    def __init__(
        self,
        *,
        sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ,
        audio_format: str = DEFAULT_AUDIO_FORMAT,
        ms_per_char: float = 60.0,
        min_ms: float = 200.0,
        max_ms: float = 8000.0,
        frequency_hz: float = 220.0,
    ) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        self._sample_rate_hz = sample_rate_hz
        self._audio_format = audio_format
        self._ms_per_char = ms_per_char
        self._min_ms = min_ms
        self._max_ms = max_ms
        self._frequency_hz = frequency_hz

    @property
    def audio_format(self) -> str:
        return self._audio_format

    def synthesize(self, text: str) -> bytes:
        if not text or not text.strip():
            raise EmptyTextError("No text to synthesize")
        duration_ms = min(self._max_ms, max(self._min_ms, len(text) * self._ms_per_char))
        return self._tone(duration_ms)

    def _tone(self, duration_ms: float) -> bytes:
        sample_count = int(self._sample_rate_hz * duration_ms / 1000)
        samples = array.array("h")
        amplitude = 12000
        step = 2 * math.pi * self._frequency_hz / self._sample_rate_hz
        for i in range(sample_count):
            samples.append(int(amplitude * math.sin(step * i)))
        return samples.tobytes()
