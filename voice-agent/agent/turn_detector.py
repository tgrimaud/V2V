"""Server-side turn detection (endpointing) for PCM 16-bit mono audio.

Used for transports that have no client-side VAD (e.g. telephony / SIP, where
there is no browser to run Silero). The detector consumes raw PCM frames,
classifies each short frame as speech or silence via short-term energy (RMS),
and signals end-of-turn once a minimum amount of speech has been followed by a
configurable trailing silence.

Pure, dependency-free and deterministic so it can be unit-tested with synthetic
PCM (zeros for silence, high-amplitude samples for speech).
"""

from array import array
from dataclasses import dataclass, field

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # bytes per sample (16-bit)


@dataclass
class TurnDetectorConfig:
    rms_threshold: float = 500.0  # RMS amplitude above which a frame is "speech"
    silence_ms: int = 500         # trailing silence that ends a turn
    min_speech_ms: int = 200      # minimum speech before a turn may end
    frame_ms: int = 20            # analysis frame size
    sample_rate: int = SAMPLE_RATE  # 16000 for web PCM, 8000 for telephony

    def frame_bytes(self) -> int:
        return int(self.sample_rate * self.frame_ms / 1000) * SAMPLE_WIDTH


def frame_rms(frame: bytes) -> float:
    """Root-mean-square amplitude of a 16-bit mono PCM frame."""
    if len(frame) < SAMPLE_WIDTH:
        return 0.0
    samples = array("h")
    usable = len(frame) - (len(frame) % SAMPLE_WIDTH)
    samples.frombytes(frame[:usable])
    if not samples:
        return 0.0
    total = sum(s * s for s in samples)
    return (total / len(samples)) ** 0.5


@dataclass
class TurnDetector:
    """Stateful end-of-turn detector fed incrementally with PCM frames."""

    config: TurnDetectorConfig = field(default_factory=TurnDetectorConfig)
    _leftover: bytearray = field(default_factory=bytearray, init=False)
    _speech_ms: int = field(default=0, init=False)
    _trailing_silence_ms: int = field(default=0, init=False)
    _has_speech: bool = field(default=False, init=False)
    _ended: bool = field(default=False, init=False)

    def reset(self) -> None:
        """Clear all state to begin detecting a new turn."""
        self._leftover = bytearray()
        self._speech_ms = 0
        self._trailing_silence_ms = 0
        self._has_speech = False
        self._ended = False

    @property
    def has_speech(self) -> bool:
        return self._has_speech

    def process(self, pcm: bytes) -> bool:
        """Feed PCM bytes; return True the first time end-of-turn is detected."""
        if self._ended:
            return False

        self._leftover.extend(pcm)
        frame_bytes = self.config.frame_bytes()

        while len(self._leftover) >= frame_bytes:
            frame = bytes(self._leftover[:frame_bytes])
            del self._leftover[:frame_bytes]
            if self._consume_frame(frame):
                self._ended = True
                return True
        return False

    def _consume_frame(self, frame: bytes) -> bool:
        if frame_rms(frame) >= self.config.rms_threshold:
            self._has_speech = True
            self._speech_ms += self.config.frame_ms
            self._trailing_silence_ms = 0
            return False

        if self._has_speech:
            self._trailing_silence_ms += self.config.frame_ms

        return (
            self._has_speech
            and self._speech_ms >= self.config.min_speech_ms
            and self._trailing_silence_ms >= self.config.silence_ms
        )
