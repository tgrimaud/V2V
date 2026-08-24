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
# Safe floor for a tuned-down hold (TASK-WEB-015 lever 3). Shortening the window
# cuts latency but raises the false-endpoint (premature cut) risk: too low and a
# natural mid-sentence pause is read as end-of-turn. The signaling env reader
# clamps any tuning to this floor so a misconfiguration can never drop it into the
# constant-premature-cut regime. Confirm the real false-cut rate on live audio
# before lowering the deployed value toward it.
MIN_SAFE_SILENCE_WINDOW_MS = 250.0
# Peak |amplitude| above which a frame counts as speech. ~3% of int16 full scale
# (32767); low enough to catch quiet speech, high enough to reject line noise.
DEFAULT_AMPLITUDE_THRESHOLD = 1000

SIGNAL_SILENCE_WINDOW = "silence_window"
SIGNAL_CLIENT_STOP = "client_stop"
# Control-plane end-of-turn (TASK-WEB-029): the turn is finalized by a pluggable control
# signal (WS client / Genesys protocol / tests) rather than the energy detector's silence
# window. No measured slice_ms — it is not a silence-window measurement.
SIGNAL_CONTROL_EOT = "control_end_of_turn"

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


# Default minimum voiced duration for a chunk to count as a turn; guards a single
# click / cough from being flushed as an utterance in the streaming path.
DEFAULT_MIN_UTTERANCE_MS = 200.0


@dataclass(frozen=True)
class StreamingTurnDecision:
    """Per-frame outcome of the streaming detector.

    `detection` present -> end-of-turn fired, flush the buffered utterance now.
    `discard` -> a sub-`min_utterance_ms` click terminated; drop the buffer, no turn.
    Both absent -> keep buffering.
    """

    detection: EndOfTurnResult | None = None
    discard: bool = False


_NO_DECISION = StreamingTurnDecision()


class StreamingEndOfTurnDetector:
    """Frame-incremental sibling of `EndOfTurnDetector` (TASK-STT-012).

    The batch detector inspects a fully captured buffer after the fact; this one
    consumes audio chunks as they stream and fires the same `EndOfTurnResult` /
    `voice.end_of_turn` span contract **before** the whole utterance is available,
    as soon as `silence_window_ms` of trailing silence follows speech. It keeps the
    TASK-STT-009 guarantee: with no speech it never invents a turn boundary
    (`observe`/`finish` return no detection).

    State machine per turn (reset after each terminal decision):
    speech frames extend the utterance; once speech has been seen, accumulated
    silence >= the window fires the turn. `finish()` is the streaming analog of the
    batch `client_stop` fallback: on stream end (EndFrame / call drop) it flushes
    pending speech even if the full window has not elapsed.
    """

    def __init__(
        self,
        *,
        sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ,
        silence_window_ms: float = DEFAULT_SILENCE_WINDOW_MS,
        amplitude_threshold: int = DEFAULT_AMPLITUDE_THRESHOLD,
        min_utterance_ms: float = DEFAULT_MIN_UTTERANCE_MS,
        num_channels: int = 1,
    ) -> None:
        if sample_rate_hz <= 0 or num_channels <= 0:
            raise ValueError("sample_rate_hz and num_channels must be positive")
        self._sample_rate_hz = sample_rate_hz
        self._silence_window_ms = silence_window_ms
        self._amplitude_threshold = amplitude_threshold
        self._min_utterance_ms = min_utterance_ms
        self._num_channels = num_channels
        self.reset()

    def observe(self, audio: bytes) -> StreamingTurnDecision:
        frame_ms = self._frame_duration_ms(audio)
        self._elapsed_ms += frame_ms
        if self._is_speech(audio):
            self._has_speech = True
            self._speech_ms += frame_ms
            self._speech_end_ms = self._elapsed_ms
            self._trailing_silence_ms = 0.0
            return _NO_DECISION
        if not self._has_speech:
            # Leading silence before any speech -> no boundary to invent yet.
            return _NO_DECISION
        self._trailing_silence_ms += frame_ms
        if self._trailing_silence_ms < self._silence_window_ms:
            return _NO_DECISION
        return self._terminate(SIGNAL_SILENCE_WINDOW, self._silence_window_ms)

    def finish(self) -> StreamingTurnDecision:
        """Stream end (EndFrame / call drop): flush pending speech as a client stop."""
        if not self._has_speech:
            self.reset()
            return _NO_DECISION
        return self._terminate(SIGNAL_CLIENT_STOP, self._trailing_silence_ms)

    @property
    def has_speech(self) -> bool:
        """True once speech has been observed in the current (not-yet-terminated) turn.

        Lets the streaming STT path open the provider connection only when the
        customer actually starts speaking, instead of streaming inter-turn silence.
        """
        return self._has_speech

    @property
    def silence_window_ms(self) -> float:
        """The configured trailing-silence hold (TASK-WEB-015 lever 3).

        Exposed so the STT processor can stamp the *configured* window on the
        `voice.end_of_turn` telemetry: on a `client_stop` turn `slice_ms` is the real
        (short) trailing silence, not the window, so QA needs the configured value to
        analyse the false-cut rate against the deployed hold.
        """
        return self._silence_window_ms

    def reset(self) -> None:
        self._elapsed_ms = 0.0
        self._speech_ms = 0.0
        self._speech_end_ms: float | None = None
        self._trailing_silence_ms = 0.0
        self._has_speech = False

    def _terminate(self, signal: str, slice_ms: float) -> StreamingTurnDecision:
        if self._speech_ms < self._min_utterance_ms:
            self.reset()
            return StreamingTurnDecision(discard=True)
        detection = EndOfTurnResult(
            True, signal, self._speech_end_ms, self._trailing_silence_ms, slice_ms
        )
        self.reset()
        return StreamingTurnDecision(detection=detection)

    def _is_speech(self, audio: bytes) -> bool:
        samples = _pcm16_samples(audio)
        return bool(samples) and _peak_amplitude(samples) >= self._amplitude_threshold

    def _frame_duration_ms(self, audio: bytes) -> float:
        sample_count = (len(audio) // 2) // max(1, self._num_channels)
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
