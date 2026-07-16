"""Pipecat STT frame processor (Sprint 4 / TASK-WEB-005, ST-2).

Consumes a whole-utterance `InputAudioRawFrame` and emits a `TranscriptionFrame`,
delegating to the existing web voice STT ingress so the `web.voice.ingress` +
`stt.*` telemetry, sanitization and outcomes are identical to the stdlib path. This
is the *batch* wrapper: it transcribes the full utterance in one call (streaming
partials are Sprint 5).

The ingress collaborator is injected (duck-typed `SttIngress`) so this module never
imports `web_voice` (whose package init also pulls the TTS half) nor `tts_synthesis`.
That keeps the hard STT/TTS separation enforced by the architecture test.
"""

import asyncio
from typing import Any, Protocol

from pipecat.frames.frames import Frame, InputAudioRawFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from stt_validation.models import SttOutcome, TranscriptResult


class SttIngress(Protocol):
    """The subset of `WebVoiceIngress` this processor delegates to."""

    def transcribe_turn(
        self,
        audio: bytes,
        envelope: Any,
        telemetry: Any = None,
        *,
        received_ms: float | None = None,
        detect_end_of_turn: bool = True,
    ) -> TranscriptResult: ...


class SttFrameProcessor(FrameProcessor):
    """`InputAudioRawFrame` -> `TranscriptionFrame` via the STT ingress (batch)."""

    def __init__(
        self,
        ingress: SttIngress,
        envelope: Any,
        telemetry: Any = None,
        *,
        received_ms: float | None = None,
        detect_end_of_turn: bool = True,
    ) -> None:
        super().__init__()
        self._ingress = ingress
        self._envelope = envelope
        self._telemetry = telemetry
        self._received_ms = received_ms
        # False on the streaming path, where the utterance aggregator owns
        # incremental end-of-turn detection and its span (TASK-STT-012).
        self._detect_end_of_turn = detect_end_of_turn
        # Last transcription outcome, read by the turn processor to build the
        # HTTP response (a non-success turn produces no downstream frame).
        self.result: TranscriptResult | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            await self._transcribe(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _transcribe(self, frame: InputAudioRawFrame, direction: FrameDirection) -> None:
        # The ingress does blocking work (temp file + provider I/O); keep it off the
        # pipeline event loop.
        result = await asyncio.to_thread(
            self._ingress.transcribe_turn,
            frame.audio,
            self._envelope,
            self._telemetry,
            received_ms=self._received_ms,
            detect_end_of_turn=self._detect_end_of_turn,
        )
        self.result = result
        if result.outcome is SttOutcome.SUCCESS:
            user_id = getattr(self._envelope, "external_session_id", "") or "web"
            await self.push_frame(
                TranscriptionFrame(text=result.transcript, user_id=user_id, timestamp=""),
                direction,
            )
        # Non-success (FAILED / UNAVAILABLE): never invent a transcript, so nothing
        # flows downstream; the outcome is surfaced via `self.result`.
