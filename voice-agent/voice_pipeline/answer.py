"""Backend answer step (TASK-WEB-003-D): transcript -> backend answer -> text.

Replaces the echo step: instead of speaking the transcript back, the loop asks the
`BackendAnswerPort` for a response and speaks that. Both runtimes share this module
so they stay behaviourally equivalent — the Pipecat pipeline runs `AnswerProcessor`,
the stdlib runtime calls `answer_with_telemetry` directly.

It imports only pipecat, the neutral `conversation_backend` contract and the shared
`voice_common` telemetry; it never imports `stt_validation`, `tts_synthesis` or
`web_voice`, preserving the STT/TTS separation (enforced by the architecture test).
"""

import asyncio
from typing import Any

from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from conversation_backend import AnswerOutcome, AnswerRequest, BackendAnswerPort, EmptyTranscriptError
from voice_common.telemetry import TelemetryRecorder, Timer

# The backend latency slice (US-036, registered in voice_common/pipeline_timing.py).
# `backend.first_token` is the time-to-first-token slice; `backend.request` is the
# total answer duration. Both carry the correlation id, provider, outcome and length.
BACKEND_FIRST_TOKEN_SPAN = "backend.first_token"
BACKEND_REQUEST_SPAN = "backend.request"


def answer_with_telemetry(
    backend: BackendAnswerPort,
    request: AnswerRequest,
    telemetry: TelemetryRecorder | None,
) -> Any:
    """Call the backend, timing it and emitting the backend spans + outcome event.

    Emits both `backend.first_token` and `backend.request`. This backend is batch
    (non-streaming): the single answer arrives at once, so first-token latency equals
    the total request latency. A future streaming backend (HTTP, TASK-WEB-003-C) would
    stamp `backend.first_token` at the first chunk and `backend.request` at completion.
    Only lengths are exposed (never the raw transcript or answer text), matching the
    privacy rule of the conversation contract's `to_dict`.
    """
    timer = Timer()
    result = backend.answer(request)
    duration_ms = timer.elapsed_ms()
    if telemetry is not None:
        attrs = {
            "correlation_id": request.correlation_id,
            "channel": request.channel,
            "provider": backend.name,
            "outcome": result.outcome.value,
            "answer_chars": len(result.text),
        }
        telemetry.span(BACKEND_FIRST_TOKEN_SPAN, duration_ms, **attrs)
        telemetry.span(BACKEND_REQUEST_SPAN, duration_ms, **attrs)
        telemetry.record("voice.backend.answered", backend_request_ms=round(duration_ms, 3), **attrs)
    return result


class AnswerProcessor(FrameProcessor):
    """`TranscriptionFrame` -> backend answer -> plain `TextFrame` (replaces echo)."""

    def __init__(self, backend: BackendAnswerPort, envelope: Any, telemetry: Any = None) -> None:
        super().__init__()
        self._backend = backend
        self._envelope = envelope
        self._telemetry = telemetry
        # Last AnswerResult, read by the pipeline / turn processor for the response.
        self.result: Any = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            await self._answer(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _answer(self, frame: TranscriptionFrame, direction: FrameDirection) -> None:
        request = AnswerRequest.from_envelope(frame.text, self._envelope)
        try:
            # The backend does blocking work (adapter I/O later); keep it off the loop.
            result = await asyncio.to_thread(
                answer_with_telemetry, self._backend, request, self._telemetry
            )
        except EmptyTranscriptError:
            # Nothing to answer: never invent a turn, so no text flows downstream.
            self.result = None
            return
        self.result = result
        if result.text and result.outcome is not AnswerOutcome.UNAVAILABLE:
            await self.push_frame(TextFrame(text=result.text), direction)
