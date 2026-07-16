"""Streaming STT frame processor for the WebRTC path (TASK-STT-010).

Replaces the batch `[UtteranceAggregator -> SttFrameProcessor]` pair on the
streaming path. Instead of buffering a whole utterance and transcribing it in one
call after end-of-turn, it streams audio to Gradium's WebSocket ASR **while the
customer speaks** (`GradiumStreamingSttProvider`), pushes `InterimTranscriptionFrame`
partials as they arrive, and finalizes the moment the validated
`StreamingEndOfTurnDetector` (TASK-STT-012) reports end-of-turn — so the final
transcript lands ~0.8 s after the customer stops instead of paying the full
clip-length batch cost (see `docs/qa/stt-010-streaming-stt-spike.md`).

This processor owns the `voice.end_of_turn` span on this path (same contract as the
aggregator it replaces) and adds `time_to_first_partial` / `time_to_final` on the
`stt` slice so US-036 reports both. It lives in `web_voice` (the WebRTC composition
layer), keeping the transport-agnostic `voice_pipeline` STT service free of the
streaming provider + detector wiring.
"""

import asyncio
from typing import Any

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from stt_validation.models import SttOutcome
from stt_validation.streaming import FinalTranscript, StreamingSttError
from voice_common.sanitization import sanitize_error
from voice_common.telemetry import Timer

from .end_of_turn import (
    DEFAULT_AMPLITUDE_THRESHOLD,
    DEFAULT_MIN_UTTERANCE_MS,
    DEFAULT_SAMPLE_RATE_HZ,
    DEFAULT_SILENCE_WINDOW_MS,
    END_OF_TURN_SPAN,
    EndOfTurnResult,
    StreamingEndOfTurnDetector,
)

DEFAULT_PROVIDER_NAME = "gradium-stt-streaming"
STT_REQUEST_SPAN = "stt.request"
# The final transcript should land ~1 s after end-of-turn; cap the wait so a stalled
# provider fails the turn (safe degraded reply) instead of hanging the call.
DEFAULT_FINAL_TIMEOUT_S = 10.0


class StreamingSttProcessor(FrameProcessor):
    """Continuous audio -> live partials + a final `TranscriptionFrame` via streaming STT."""

    def __init__(
        self,
        provider: Any,
        envelope: Any,
        telemetry: Any = None,
        *,
        detector: StreamingEndOfTurnDetector | None = None,
        provider_name: str = DEFAULT_PROVIDER_NAME,
        sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ,
        final_timeout_s: float = DEFAULT_FINAL_TIMEOUT_S,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._envelope = envelope
        self._telemetry = telemetry
        self._provider_name = provider_name
        self._final_timeout_s = final_timeout_s
        self._detector = detector or StreamingEndOfTurnDetector(
            sample_rate_hz=sample_rate_hz,
            silence_window_ms=DEFAULT_SILENCE_WINDOW_MS,
            amplitude_threshold=DEFAULT_AMPLITUDE_THRESHOLD,
            min_utterance_ms=DEFAULT_MIN_UTTERANCE_MS,
        )
        self._user_id = getattr(envelope, "external_session_id", "") or "web"
        self._session: Any = None
        self._turn_timer: Timer | None = None
        self._first_partial_ms: float | None = None
        # Read by tests: number of final transcripts emitted this session.
        self.final_count = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            await self._on_audio(frame, direction)
        elif isinstance(frame, EndFrame):
            await self._on_end(direction)
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _on_audio(self, frame: InputAudioRawFrame, direction: FrameDirection) -> None:
        decision = self._detector.observe(frame.audio)
        if self._detector.has_speech and self._session is None:
            await self._open_session()
        if self._session is not None:
            await self._session.send_audio(frame.audio)
            await self._emit_partials(self._session, direction)
        if decision.detection is not None:
            await self._finalize(decision.detection, direction)
        elif decision.discard:
            await self._discard_session()

    async def _on_end(self, direction: FrameDirection) -> None:
        decision = self._detector.finish()
        if decision.detection is not None:
            await self._finalize(decision.detection, direction)
        else:
            await self._discard_session()

    async def _open_session(self) -> None:
        self._session = await self._provider.open()
        self._turn_timer = Timer()
        self._first_partial_ms = None

    async def _emit_partials(self, session: Any, direction: FrameDirection) -> None:
        for partial in session.poll_partials():
            if self._first_partial_ms is None and self._turn_timer is not None:
                self._first_partial_ms = self._turn_timer.elapsed_ms()
            await self.push_frame(
                InterimTranscriptionFrame(text=partial.text, user_id=self._user_id, timestamp=""),
                direction,
            )

    async def _finalize(self, detection: EndOfTurnResult, direction: FrameDirection) -> None:
        self._record_end_of_turn(detection)
        session = self._session
        self._session = None
        if session is None:
            return
        tail = Timer()
        try:
            await session.finish()
            final = await asyncio.wait_for(session.wait_final(), self._final_timeout_s)
        except (StreamingSttError, asyncio.TimeoutError) as exc:
            await session.aclose()
            self._emit_stt_failure(exc, tail.elapsed_ms())
            return
        await self._emit_partials(session, direction)
        await session.aclose()
        await self._emit_final(final, tail.elapsed_ms(), direction)

    async def _emit_final(self, final: FinalTranscript, tail_ms: float, direction: FrameDirection) -> None:
        transcript = final.text.strip()
        outcome = SttOutcome.SUCCESS if transcript else SttOutcome.UNAVAILABLE
        self._emit_stt_telemetry(outcome, tail_ms)
        if transcript:
            self.final_count += 1
            await self.push_frame(
                TranscriptionFrame(text=final.text, user_id=self._user_id, timestamp=""),
                direction,
            )

    async def _discard_session(self) -> None:
        if self._session is not None:
            await self._session.aclose()
            self._session = None

    def _record_end_of_turn(self, detection: EndOfTurnResult) -> None:
        if self._telemetry is None or self._envelope is None or detection.slice_ms is None:
            return
        attrs = self._end_of_turn_attrs(detection)
        self._telemetry.span(END_OF_TURN_SPAN, detection.slice_ms, **attrs)
        self._telemetry.record("voice.end_of_turn.detected", **attrs)

    def _end_of_turn_attrs(self, detection: EndOfTurnResult) -> dict[str, Any]:
        return {
            "correlation_id": self._envelope.correlation_id,
            "channel": getattr(self._envelope, "channel", None),
            "provider": self._provider_name,
            "end_of_turn_signal": detection.signal,
            "trailing_silence_ms": round(detection.trailing_silence_ms, 3),
            "speech_end_ms": round(detection.speech_end_ms, 3)
            if detection.speech_end_ms is not None
            else None,
        }

    def _emit_stt_telemetry(self, outcome: SttOutcome, tail_ms: float) -> None:
        if self._telemetry is None or self._envelope is None:
            return
        attrs = self._stt_attrs(outcome.value)
        self._telemetry.span(STT_REQUEST_SPAN, tail_ms, **attrs)
        first_partial = round(self._first_partial_ms, 3) if self._first_partial_ms is not None else None
        record = "stt.transcript.final" if outcome is SttOutcome.SUCCESS else "stt.unavailable"
        self._telemetry.record(
            record,
            time_to_first_partial_ms=first_partial,
            time_to_final_ms=round(tail_ms, 3),
            **attrs,
        )
        self._telemetry.metric("stt.time_to_final_ms", tail_ms, **attrs)
        if self._first_partial_ms is not None:
            self._telemetry.metric("stt.time_to_first_partial_ms", self._first_partial_ms, **attrs)

    def _emit_stt_failure(self, exc: Exception, tail_ms: float) -> None:
        if self._telemetry is None or self._envelope is None:
            return
        sanitized = sanitize_error(exc, domain="stt")
        attrs = self._stt_attrs(SttOutcome.FAILED.value)
        self._telemetry.span(STT_REQUEST_SPAN, tail_ms, **attrs)
        self._telemetry.record(
            "stt.failure",
            error_code=sanitized.reason_code,
            error_reason=sanitized.reason,
            time_to_final_ms=round(tail_ms, 3),
            **attrs,
        )

    def _stt_attrs(self, outcome: str) -> dict[str, Any]:
        return {
            "correlation_id": self._envelope.correlation_id,
            "provider": self._provider_name,
            "outcome": outcome,
        }
