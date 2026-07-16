"""Utterance aggregator for the streaming WebRTC path (Sprint 6).

The WebRTC transport emits continuous small `InputAudioRawFrame` chunks, but the
Sprint 4/5 STT stage is *batch* (one whole-utterance frame per turn). This processor
bridges the two: it buffers incoming PCM and flushes one whole-utterance
`InputAudioRawFrame` downstream when a `StreamingEndOfTurnDetector` (TASK-STT-012)
fires an end-of-turn.

Turn detection is delegated to the frame-incremental `StreamingEndOfTurnDetector`,
which is the streaming sibling of the batch `EndOfTurnDetector` and owns the
`voice.end_of_turn` span for this path (TASK-STT-012 replaces the interim
WEB-007 energy heuristic that lived inline here). The aggregator only owns the
audio buffer and emits the span/event when the detector reports a turn, so the
US-036 `end_of_turn` slice is measured at the real streaming moment instead of
being re-derived by the batch detector inside the ingress.

Scope guard: no barge-in (TASK-WEB-008) — while the bot speaks, incoming mic frames
are still buffered; controlled demos use headphones to avoid the bot echoing into
its own aggregator.

End-of-turn depends on receiving sub-threshold "silence" frames: a real microphone
emits an ambient noise floor, so Opus keeps sending packets and the trailing-silence
window fills. **Pure digital silence triggers Opus DTX** (no packets), so a synthetic
file-based test clip must pad the tail with low-amplitude noise (peak << the speech
threshold), never zeros, or no end-of-turn is ever detected.
"""

from typing import Any

from pipecat.frames.frames import EndFrame, Frame, InputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from .end_of_turn import (
    DEFAULT_AMPLITUDE_THRESHOLD,
    DEFAULT_MIN_UTTERANCE_MS,
    DEFAULT_SAMPLE_RATE_HZ,
    DEFAULT_SILENCE_WINDOW_MS,
    END_OF_TURN_SPAN,
    EndOfTurnResult,
    StreamingEndOfTurnDetector,
)

DEFAULT_PROVIDER_NAME = "webrtc"


class UtteranceAggregator(FrameProcessor):
    """Buffers streamed PCM and flushes one whole-utterance frame on end-of-turn.

    Turn boundaries come from an injected `StreamingEndOfTurnDetector`; when it fires
    the aggregator records the `voice.end_of_turn` span (if telemetry + envelope were
    provided) and flushes the buffered utterance downstream.
    """

    def __init__(
        self,
        *,
        sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ,
        silence_window_ms: float = DEFAULT_SILENCE_WINDOW_MS,
        amplitude_threshold: int = DEFAULT_AMPLITUDE_THRESHOLD,
        min_utterance_ms: float = DEFAULT_MIN_UTTERANCE_MS,
        num_channels: int = 1,
        detector: StreamingEndOfTurnDetector | None = None,
        telemetry: Any = None,
        envelope: Any = None,
        provider_name: str = DEFAULT_PROVIDER_NAME,
    ) -> None:
        super().__init__()
        self._sample_rate_hz = sample_rate_hz
        self._num_channels = num_channels
        self._detector = detector or StreamingEndOfTurnDetector(
            sample_rate_hz=sample_rate_hz,
            silence_window_ms=silence_window_ms,
            amplitude_threshold=amplitude_threshold,
            min_utterance_ms=min_utterance_ms,
            num_channels=num_channels,
        )
        self._telemetry = telemetry
        self._envelope = envelope
        self._provider_name = provider_name
        self._buffer = bytearray()
        # Read by tests / telemetry: number of utterances flushed this session.
        self.flush_count = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            await self._accumulate(frame, direction)
        elif isinstance(frame, EndFrame):
            await self._finish(direction)
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _accumulate(self, frame: InputAudioRawFrame, direction: FrameDirection) -> None:
        self._buffer.extend(frame.audio)
        await self._apply(self._detector.observe(frame.audio), direction)

    async def _finish(self, direction: FrameDirection) -> None:
        await self._apply(self._detector.finish(), direction)

    async def _apply(self, decision, direction: FrameDirection) -> None:
        if decision.detection is not None:
            await self._emit_and_flush(decision.detection, direction)
        elif decision.discard:
            self._buffer = bytearray()

    async def _emit_and_flush(self, detection: EndOfTurnResult, direction: FrameDirection) -> None:
        self._record_end_of_turn(detection)
        utterance = bytes(self._buffer)
        self._buffer = bytearray()
        self.flush_count += 1
        await self.push_frame(
            InputAudioRawFrame(
                audio=utterance,
                sample_rate=self._sample_rate_hz,
                num_channels=self._num_channels,
            ),
            direction,
        )

    def _record_end_of_turn(self, detection: EndOfTurnResult) -> None:
        if self._telemetry is None or self._envelope is None or detection.slice_ms is None:
            return
        attrs = {
            "correlation_id": self._envelope.correlation_id,
            "channel": getattr(self._envelope, "channel", None),
            "provider": self._provider_name,
            "end_of_turn_signal": detection.signal,
            "trailing_silence_ms": round(detection.trailing_silence_ms, 3),
            "speech_end_ms": round(detection.speech_end_ms, 3)
            if detection.speech_end_ms is not None
            else None,
        }
        self._telemetry.span(END_OF_TURN_SPAN, detection.slice_ms, **attrs)
        self._telemetry.record("voice.end_of_turn.detected", **attrs)
