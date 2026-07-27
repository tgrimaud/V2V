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
import os
from typing import Any

from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from conversation_backend import (
    BACKEND_UNAVAILABLE_REASON,
    DEFAULT_CONFIDENCE_THRESHOLD,
    EMPTY_ANSWER_REASON,
    LOW_CONFIDENCE_REASON,
    AnswerOutcome,
    AnswerRequest,
    AnswerResult,
    BackendAnswerPort,
    EmptyTranscriptError,
    degraded_answer,
)
from voice_common.sanitization import sanitize_error
from voice_common.telemetry import TelemetryRecorder, Timer

# The backend latency slice (US-036, registered in voice_common/pipeline_timing.py).
# `backend.first_token` is the time-to-first-token slice; `backend.request` is the
# total answer duration. Both carry the correlation id, provider, outcome and length.
BACKEND_FIRST_TOKEN_SPAN = "backend.first_token"
BACKEND_REQUEST_SPAN = "backend.request"

# RF-022 (ADR-0034): the client-side degraded-mode confidence floor is env-tunable so a
# deployment can align it with the backend's own confidence policy without a code change.
# It is a *safety net* below the backend grounding guardrail, not a replacement for it.
CONFIDENCE_THRESHOLD_ENV_VAR = "VOICE_BACKEND_CONFIDENCE_THRESHOLD"


def resolve_confidence_threshold() -> float:
    """Resolve the degraded-mode confidence floor from the environment.

    Falls back to `DEFAULT_CONFIDENCE_THRESHOLD` when the override is unset, non-numeric
    or out of the [0, 1] range, so a bad value degrades gracefully rather than crashing
    the turn (mirrors the barge-in env parsing in `web_voice/webrtc_signaling.py`).
    """
    raw = os.environ.get(CONFIDENCE_THRESHOLD_ENV_VAR)
    if raw is None:
        return DEFAULT_CONFIDENCE_THRESHOLD
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_CONFIDENCE_THRESHOLD
    if not 0.0 <= value <= 1.0:
        return DEFAULT_CONFIDENCE_THRESHOLD
    return value


def answer_with_telemetry(
    backend: BackendAnswerPort,
    request: AnswerRequest,
    telemetry: TelemetryRecorder | None,
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> AnswerResult:
    """Call the backend, applying the degraded-mode policy and emitting telemetry.

    Emits both `backend.first_token` and `backend.request`. This backend is batch
    (non-streaming): the single answer arrives at once, so first-token latency equals
    the total request latency. A future streaming backend (HTTP, TASK-WEB-003-C) would
    stamp `backend.first_token` at the first chunk and `backend.request` at completion.

    Degraded mode (TASK-WEB-003-F): a backend failure never crashes the turn and a
    low-confidence or empty answer is never spoken as-is. Both are replaced by the safe
    fallback (a DEGRADED result) so the customer always hears something safe and no
    content is invented. Only lengths and sanitized reasons are exposed (never the raw
    transcript, answer text or provider error string).
    """
    timer = Timer()
    try:
        result = backend.answer(request)
    except EmptyTranscriptError:
        # Nothing to answer (empty transcript): not a failure; the caller stays silent.
        raise
    except Exception as exc:  # noqa: BLE001 - any adapter fault degrades to a safe reply
        result = _unavailable_fallback(backend, request, exc)
    else:
        result = _apply_confidence_policy(request, result, confidence_threshold)
    duration_ms = timer.elapsed_ms()
    _emit_backend_telemetry(backend, request, result, duration_ms, telemetry)
    return result


def _unavailable_fallback(backend: BackendAnswerPort, request: AnswerRequest, exc: Exception) -> AnswerResult:
    sanitized = sanitize_error(exc, domain="backend")
    return degraded_answer(
        request,
        provider=backend.name,
        degraded_reason=BACKEND_UNAVAILABLE_REASON,
        error_code=sanitized.reason_code,
        error_reason=sanitized.reason,
    )


def _apply_confidence_policy(request: AnswerRequest, result: AnswerResult, threshold: float) -> AnswerResult:
    if result.outcome is AnswerOutcome.UNAVAILABLE:
        return result  # nothing to answer; never fabricate a spoken turn
    if result.confidence is not None and result.confidence < threshold:
        return degraded_answer(
            request, provider=result.provider, degraded_reason=LOW_CONFIDENCE_REASON, confidence=result.confidence
        )
    if not result.text.strip():
        # A confident but empty answer is unusable: speak the safe fallback instead.
        return degraded_answer(
            request,
            provider=result.provider,
            degraded_reason=result.degraded_reason or EMPTY_ANSWER_REASON,
            confidence=result.confidence,
            error_code=result.error_code,
            error_reason=result.error_reason,
        )
    return result


def _emit_backend_telemetry(
    backend: BackendAnswerPort,
    request: AnswerRequest,
    result: AnswerResult,
    duration_ms: float,
    telemetry: TelemetryRecorder | None,
) -> None:
    if telemetry is None:
        return
    attrs = _backend_attributes(backend, request, result)
    telemetry.span(BACKEND_FIRST_TOKEN_SPAN, duration_ms, **attrs)
    telemetry.span(BACKEND_REQUEST_SPAN, duration_ms, **attrs)
    telemetry.record("voice.backend.answered", backend_request_ms=round(duration_ms, 3), **attrs)
    if result.outcome is AnswerOutcome.DEGRADED:
        telemetry.log("warning", "backend degraded fallback served", **attrs)


def _backend_attributes(backend: BackendAnswerPort, request: AnswerRequest, result: AnswerResult) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "correlation_id": request.correlation_id,
        "channel": request.channel,
        "provider": result.provider or backend.name,
        "outcome": result.outcome.value,
        "answer_chars": len(result.text),
        "degraded": result.outcome is AnswerOutcome.DEGRADED,
    }
    if result.degraded_reason:
        attrs["degraded_reason"] = result.degraded_reason
    if result.error_code:
        attrs["error_code"] = result.error_code
    if result.error_reason:
        attrs["error_reason"] = result.error_reason
    return attrs


class AnswerProcessor(FrameProcessor):
    """`TranscriptionFrame` -> backend answer -> plain `TextFrame` (replaces echo)."""

    def __init__(
        self,
        backend: BackendAnswerPort,
        envelope: Any,
        telemetry: Any = None,
        *,
        confidence_threshold: float | None = None,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._envelope = envelope
        self._telemetry = telemetry
        # RF-022: resolve the env-tunable floor once at construction; an explicit override
        # (tests / callers) still wins over the environment.
        self._confidence_threshold = (
            confidence_threshold if confidence_threshold is not None else resolve_confidence_threshold()
        )
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
                lambda: answer_with_telemetry(
                    self._backend,
                    request,
                    self._telemetry,
                    confidence_threshold=self._confidence_threshold,
                )
            )
        except EmptyTranscriptError:
            # Nothing to answer: never invent a turn, so no text flows downstream.
            self.result = None
            return
        self.result = result
        if result.text and result.outcome is not AnswerOutcome.UNAVAILABLE:
            await self.push_frame(TextFrame(text=result.text), direction)
