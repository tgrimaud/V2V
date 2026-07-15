"""Utterance aggregator for the streaming WebRTC path (Sprint 6 / TASK-WEB-007).

The WebRTC transport emits continuous small `InputAudioRawFrame` chunks, but the
Sprint 4/5 STT stage is *batch* (one whole-utterance frame per turn). This processor
bridges the two **without** pulling in streaming STT (TASK-STT-010) or the Silero VAD
ticket (TASK-STT-012): it buffers incoming PCM and, using the project's existing
energy-based end-of-turn thresholds (TASK-STT-009, `end_of_turn.py`), flushes one
whole-utterance `InputAudioRawFrame` downstream when the speaker pauses.

It is an interim segmenter, exactly the "drop-in replacement" the `EndOfTurnDetector`
docstring anticipates: TASK-STT-012 will replace this energy heuristic with a real
streaming VAD and its own telemetry. The thresholds are reused so behaviour stays
consistent with the batch `/turn` path.

Scope guard: no barge-in (TASK-WEB-008) — while the bot speaks, incoming mic frames
are still buffered; controlled demos use headphones to avoid the bot echoing into
its own aggregator.
"""

from typing import Any

from pipecat.frames.frames import Frame, InputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from .end_of_turn import (
    DEFAULT_AMPLITUDE_THRESHOLD,
    DEFAULT_SAMPLE_RATE_HZ,
    DEFAULT_SILENCE_WINDOW_MS,
    _peak_amplitude,
    _pcm16_samples,
)


class UtteranceAggregator(FrameProcessor):
    """Buffers streamed PCM and flushes one whole-utterance frame on end-of-turn.

    An utterance is flushed once speech has been seen and a trailing silence of
    `silence_window_ms` has elapsed. `min_utterance_ms` guards against flushing a
    single click as a turn.
    """

    def __init__(
        self,
        *,
        sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ,
        silence_window_ms: float = DEFAULT_SILENCE_WINDOW_MS,
        amplitude_threshold: int = DEFAULT_AMPLITUDE_THRESHOLD,
        min_utterance_ms: float = 200.0,
        num_channels: int = 1,
    ) -> None:
        super().__init__()
        self._sample_rate_hz = sample_rate_hz
        self._silence_window_ms = silence_window_ms
        self._amplitude_threshold = amplitude_threshold
        self._min_utterance_ms = min_utterance_ms
        self._num_channels = num_channels
        self._buffer = bytearray()
        self._has_speech = False
        self._trailing_silence_ms = 0.0
        self._speech_ms = 0.0
        # Optional hook so tests / telemetry can observe each flushed utterance.
        self.flush_count = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            await self._accumulate(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _accumulate(self, frame: InputAudioRawFrame, direction: FrameDirection) -> None:
        frame_ms = self._frame_duration_ms(frame.audio)
        self._buffer.extend(frame.audio)
        if self._is_speech(frame.audio):
            self._has_speech = True
            self._speech_ms += frame_ms
            self._trailing_silence_ms = 0.0
        elif self._has_speech:
            self._trailing_silence_ms += frame_ms
            if self._trailing_silence_ms >= self._silence_window_ms:
                await self._flush(direction)

    async def _flush(self, direction: FrameDirection) -> None:
        if self._speech_ms < self._min_utterance_ms:
            self._reset()
            return
        utterance = bytes(self._buffer)
        self._reset()
        self.flush_count += 1
        await self.push_frame(
            InputAudioRawFrame(
                audio=utterance,
                sample_rate=self._sample_rate_hz,
                num_channels=self._num_channels,
            ),
            direction,
        )

    def _reset(self) -> None:
        self._buffer = bytearray()
        self._has_speech = False
        self._trailing_silence_ms = 0.0
        self._speech_ms = 0.0

    def _is_speech(self, audio: bytes) -> bool:
        samples = _pcm16_samples(audio)
        return bool(samples) and _peak_amplitude(samples) >= self._amplitude_threshold

    def _frame_duration_ms(self, audio: bytes) -> float:
        sample_count = (len(audio) // 2) // max(1, self._num_channels)
        return sample_count / self._sample_rate_hz * 1000
