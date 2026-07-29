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
from collections.abc import Sequence
from typing import Any

from pipecat.frames.frames import Frame, StartFrame, TextFrame, TranscriptionFrame
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
from voice_pipeline.filler import (
    FILLER_SPOKEN_EVENT,
    FILLER_SPOKEN_METRIC,
    FILLER_TRIGGER_REASON,
    filler_enabled,
    pick_phrase,
    resolve_filler_phrases,
    resolve_filler_threshold_ms,
)

# The backend latency slice (US-036, registered in voice_common/pipeline_timing.py).
# `backend.first_token` is the time-to-first-token slice; `backend.request` is the
# total answer duration. Both carry the correlation id, provider, outcome and length.
BACKEND_FIRST_TOKEN_SPAN = "backend.first_token"
BACKEND_REQUEST_SPAN = "backend.request"

# RF-022 (ADR-0034): the client-side degraded-mode confidence floor is env-tunable so a
# deployment can align it with the backend's own confidence policy without a code change.
# It is a *safety net* below the backend grounding guardrail, not a replacement for it.
CONFIDENCE_THRESHOLD_ENV_VAR = "VOICE_BACKEND_CONFIDENCE_THRESHOLD"

# TASK-WEB-021 (lever 2): fire a best-effort backend warm-up (POST /warm-up) once at
# pipeline start so the first real turn does not pay the cold LLM + embedding cost. Off
# the critical path, non-blocking, and easily disabled per deployment via env.
BACKEND_WARMUP_ENV_VAR = "VOICE_BACKEND_WARMUP"
BACKEND_WARMUP_EVENT = "voice.backend.warmup"
BACKEND_WARMUP_METRIC = "voice.backend.warmup.count"


def backend_warmup_enabled() -> bool:
    """Whether to trigger the connect-time backend warm-up (default on).

    Disabled only by an explicit falsy value (`0`/`false`/`no`/`off`), so a deployment
    can turn the trigger off without a code change while it stays on by default.
    """
    raw = os.environ.get(BACKEND_WARMUP_ENV_VAR)
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off")


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
        filler_enabled_flag: bool | None = None,
        filler_threshold_ms: float | None = None,
        filler_phrases: Sequence[str] | None = None,
        backend_warmup: bool | None = None,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._envelope = envelope
        self._telemetry = telemetry
        # TASK-WEB-021: resolve the connect-time warm-up toggle once; an explicit override
        # (tests) still wins over the environment. Keeps a reference to the fire-and-forget
        # warm-up task so it is not garbage-collected before it runs.
        self._backend_warmup = backend_warmup_enabled() if backend_warmup is None else backend_warmup
        self._warmup_task: "asyncio.Task[None] | None" = None
        # RF-022: resolve the env-tunable floor once at construction; an explicit override
        # (tests / callers) still wins over the environment.
        self._confidence_threshold = (
            confidence_threshold if confidence_threshold is not None else resolve_confidence_threshold()
        )
        # TASK-WEB-019: spoken filler config resolved once; explicit overrides win over env.
        self._filler_enabled = filler_enabled() if filler_enabled_flag is None else filler_enabled_flag
        threshold_ms = filler_threshold_ms if filler_threshold_ms is not None else resolve_filler_threshold_ms()
        self._filler_threshold_s = threshold_ms / 1000.0
        self._filler_phrases = tuple(filler_phrases) if filler_phrases else resolve_filler_phrases()
        # Last AnswerResult, read by the pipeline / turn processor for the response.
        self.result: Any = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            await self._answer(frame, direction)
        else:
            if isinstance(frame, StartFrame) and self._backend_warmup and self._warmup_task is None:
                # Fire once at connect, off the critical path; never blocks StartFrame.
                self._warmup_task = asyncio.create_task(self._warm_backend())
            await self.push_frame(frame, direction)

    async def _warm_backend(self) -> None:
        """Best-effort connect-time backend warm-up (TASK-WEB-021 / lever 2).

        Calls the backend's `warm_up()` in a worker thread (blocking HTTP) so the cold
        LLM + embedding cost is paid before the first turn. Any fault is swallowed (a
        cold backend just means "not warmed"); it never breaks the connect. Skipped when
        the backend does not expose `warm_up` (e.g. a test fake), so no fake needs it.
        """
        warm = getattr(self._backend, "warm_up", None)
        if not callable(warm):
            return
        try:
            warmed = await asyncio.to_thread(warm)
        except Exception:  # noqa: BLE001 - warm-up is best-effort; never break the connect
            warmed = False
        self._emit_backend_warmup(bool(warmed))

    def _emit_backend_warmup(self, warmed: bool) -> None:
        if self._telemetry is None:
            return
        attrs = {
            "correlation_id": getattr(self._envelope, "correlation_id", None),
            "channel": getattr(self._envelope, "channel", None),
            "provider": self._backend.name,
            "outcome": "success" if warmed else "miss",
        }
        self._telemetry.record(BACKEND_WARMUP_EVENT, **attrs)
        self._telemetry.metric(BACKEND_WARMUP_METRIC, 1, **attrs)

    async def _answer(self, frame: TranscriptionFrame, direction: FrameDirection) -> None:
        request = AnswerRequest.from_envelope(frame.text, self._envelope)
        # Speak a holding phrase concurrently if the answer is slow (TASK-WEB-019).
        answered = asyncio.Event()
        filler_task = asyncio.create_task(self._run_filler(answered, request, direction))
        try:
            result = await self._call_backend(request)
            # Settle the filler before the answer so a late filler can't follow the reply.
            await self._stop_filler(answered, filler_task)
        except EmptyTranscriptError:
            # Nothing to answer: never invent a turn, so no text flows downstream.
            self.result = None
            return
        finally:
            # On any exit (empty transcript, or barge-in cancelling this turn mid-wait)
            # a still-pending filler must be dropped so it can never speak out of turn.
            self._cancel_filler(filler_task)
        self.result = result
        if result.text and result.outcome is not AnswerOutcome.UNAVAILABLE:
            await self.push_frame(TextFrame(text=result.text), direction)

    async def _call_backend(self, request: AnswerRequest) -> AnswerResult:
        # The backend does blocking work (adapter I/O later); keep it off the loop.
        return await asyncio.to_thread(
            lambda: answer_with_telemetry(
                self._backend,
                request,
                self._telemetry,
                confidence_threshold=self._confidence_threshold,
            )
        )

    async def _stop_filler(self, answered: asyncio.Event, filler_task: "asyncio.Task[None]") -> None:
        """Signal the answer is settled and let the filler task finish (fired or skipped)."""
        answered.set()
        try:
            await filler_task
        except Exception:  # noqa: BLE001 - a filler/telemetry fault must never break the turn
            pass

    def _cancel_filler(self, filler_task: "asyncio.Task[None]") -> None:
        # Best-effort drop of a still-pending filler; never awaited here so an outer
        # cancellation (barge-in) is not masked. A completed task is left untouched.
        if not filler_task.done():
            filler_task.cancel()

    async def _run_filler(
        self, answered: asyncio.Event, request: AnswerRequest, direction: FrameDirection
    ) -> None:
        """Speak one filler once the perceived-wait threshold elapses without an answer."""
        if not self._filler_enabled:
            return
        try:
            await asyncio.wait_for(answered.wait(), timeout=self._filler_threshold_s)
            return  # answered before the threshold: the wait was short, no filler needed
        except asyncio.TimeoutError:
            pass
        if answered.is_set():  # race guard: the answer landed exactly at the threshold
            return
        await self.push_frame(TextFrame(text=pick_phrase(self._filler_phrases)), direction)
        self._emit_filler_spoken(request)

    def _emit_filler_spoken(self, request: AnswerRequest) -> None:
        if self._telemetry is None:
            return
        attrs = {
            "correlation_id": request.correlation_id,
            "channel": request.channel,
            "provider": self._backend.name,
            "wait_ms": round(self._filler_threshold_s * 1000.0, 3),
            "trigger": FILLER_TRIGGER_REASON,
        }
        self._telemetry.record(FILLER_SPOKEN_EVENT, **attrs)
        self._telemetry.metric(FILLER_SPOKEN_METRIC, 1, **attrs)
