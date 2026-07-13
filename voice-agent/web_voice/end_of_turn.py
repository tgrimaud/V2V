"""End-of-turn detection for the web voice runtime (TASK-STT-009).

Owns the US-036 `end_of_turn` slice: deciding when the customer has finished
speaking. The web V1 path captures a full utterance in one buffer, so the
authoritative signal is a **trailing-silence window** over the captured PCM16,
with an **explicit client stop** as the fallback when the buffer ends before a
full silence window has elapsed. A real streaming VAD is a future, drop-in
replacement — the detector is injected into the ingress, so nothing else changes
when it is swapped.

The detector never invents a turn boundary: if the buffer holds no speech at all
(pure silence / empty), it reports `detected=False` and the ingress emits no
end-of-turn span, so the pipeline timing report simply shows the slice as
"not measured" for that turn rather than a fabricated latency.
"""

import array
import sys
from dataclasses import dataclass

DEFAULT_SAMPLE_RATE_HZ = 16000
DEFAULT_FRAME_MS = 20.0
# Trailing silence that confirms the speaker has finished. This is also the
# added latency the detector contributes once speech ends (the confirmation
# hold), which is exactly what the end_of_turn slice measures.
DEFAULT_SILENCE_WINDOW_MS = 500.0
# Peak |amplitude| above which a frame counts as speech. ~3% of int16 full scale
# (32767); low enough to catch quiet speech, high enough to reject line noise.
DEFAULT_AMPLITUDE_THRESHOLD = 1000

SIGNAL_SILENCE_WINDOW = "silence_window"
SIGNAL_CLIENT_STOP = "client_stop"

# OpenTelemetry span name for the end_of_turn slice, consumed by
# stt_validation.pipeline_timing so US-036 measures the slice.
END_OF_TURN_SPAN = "voice.end_of_turn"


@dataclass(frozen=True)
class EndOfTurnResult:
    detected: bool
    signal: str | None
    speech_end_ms: float | None
    trailing_silence_ms: float
    # Measured end-of-turn slice latency (ms); None when no turn is detected.
    slice_ms: float | None


class EndOfTurnDetector:
    def __init__(
        self,
        *,
        sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ,
        frame_ms: float = DEFAULT_FRAME_MS,
        silence_window_ms: float = DEFAULT_SILENCE_WINDOW_MS,
        amplitude_threshold: int = DEFAULT_AMPLITUDE_THRESHOLD,
    ) -> None:
        if sample_rate_hz <= 0 or frame_ms <= 0:
            raise ValueError("sample_rate_hz and frame_ms must be positive")
        self._sample_rate_hz = sample_rate_hz
        self._frame_ms = frame_ms
        self._silence_window_ms = silence_window_ms
        self._amplitude_threshold = amplitude_threshold
        self._frame_samples = max(1, int(sample_rate_hz * frame_ms / 1000))

    def detect(self, audio: bytes) -> EndOfTurnResult:
        samples = _pcm16_samples(audio)
        if not samples:
            return EndOfTurnResult(False, None, None, 0.0, None)

        last_speech_frame = self._last_speech_frame(samples)
        if last_speech_frame is None:
            return EndOfTurnResult(False, None, None, self._duration_ms(len(samples)), None)

        speech_end_ms = self._frame_end_ms(last_speech_frame, len(samples))
        trailing_silence_ms = max(0.0, self._duration_ms(len(samples)) - speech_end_ms)
        if trailing_silence_ms >= self._silence_window_ms:
            return EndOfTurnResult(
                True, SIGNAL_SILENCE_WINDOW, speech_end_ms, trailing_silence_ms, self._silence_window_ms
            )
        return EndOfTurnResult(
            True, SIGNAL_CLIENT_STOP, speech_end_ms, trailing_silence_ms, trailing_silence_ms
        )

    def _last_speech_frame(self, samples: array.array) -> int | None:
        last: int | None = None
        for frame_index, start in enumerate(range(0, len(samples), self._frame_samples)):
            frame = samples[start : start + self._frame_samples]
            if _peak_amplitude(frame) >= self._amplitude_threshold:
                last = frame_index
        return last

    def _frame_end_ms(self, frame_index: int, total_samples: int) -> float:
        end_sample = min((frame_index + 1) * self._frame_samples, total_samples)
        return self._duration_ms(end_sample)

    def _duration_ms(self, sample_count: int) -> float:
        return sample_count / self._sample_rate_hz * 1000


def _pcm16_samples(audio: bytes) -> array.array:
    # Drop a trailing odd byte so the 16-bit frame view is always well-formed.
    usable = audio[: len(audio) - (len(audio) % 2)]
    samples = array.array("h")
    samples.frombytes(usable)
    if sys.byteorder == "big":  # PCM16 is little-endian on the wire
        samples.byteswap()
    return samples


def _peak_amplitude(frame: array.array) -> int:
    peak = 0
    for sample in frame:
        magnitude = -sample if sample < 0 else sample
        if magnitude > peak:
            peak = magnitude
    return peak
