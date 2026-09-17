"""Streamed backend answer runner (TASK-WEB-020 / lever 1, ADR-0037).

Consumes the backend guarded SSE stream (`answer_stream`) and hands each vetted
sentence to the TTS **as it arrives** (via an injected async `push`), so first audio
starts on the first sentence instead of waiting for the whole answer. It is a plain
orchestrator — no pipecat import — so it is unit-testable with a fake backend, a fake
push and a fake telemetry recorder.

Safety (DEC-002): every `chunk` is already grounded + guardrail-vetted by the backend
`GuardedSentenceEmitter` (grounding first, per-sentence output guardrail, safe hand-off
as a terminal chunk on a block), so speaking chunks as they arrive never voices an
ungrounded amount. Per the Architecture/Product decision for this lever (ticket Open
Question, option A), the terminal `done` confidence is **advisory**: a grounded but
low-confidence answer is logged, not un-said (it was already spoken). A backend `error`
or an empty stream degrades to the same safe fallback the blocking path speaks.

Barge-in: an interruption cancels the runner; it aborts the in-flight SSE read
(`StreamControl.abort` closes the socket so a blocked read unblocks), emits the
interrupted outcome, and re-raises `CancelledError` so pipecat completes the
interruption — no sentence is pushed after cancellation and the connection is closed.
"""

import asyncio
from typing import Any, Awaitable, Callable

from conversation_backend import (
    CHUNK,
    DONE,
    ERROR,
    AnswerOutcome,
    AnswerRequest,
    AnswerResult,
    BACKEND_UNAVAILABLE_REASON,
    EMPTY_ANSWER_REASON,
    LOW_CONFIDENCE_REASON,
    EmptyTranscriptError,
    StreamControl,
    degraded_answer,
)
from voice_common.telemetry import Timer

# US-036 slice span names — mirror voice_pipeline.answer / voice_common.pipeline_timing
# so a streamed turn feeds the SAME backend_first_token / backend_request distributions
# (backend.first_token now = time to the FIRST sentence, the lever-1 win).
BACKEND_FIRST_TOKEN_SPAN = "backend.first_token"
BACKEND_REQUEST_SPAN = "backend.request"
BACKEND_STREAMED_EVENT = "voice.backend.streamed"
BACKEND_STREAM_INTERRUPTED_EVENT = "voice.backend.stream.interrupted"
# Advisory low-confidence signal (option A): the grounded answer was already spoken; this
# only records that its confidence was below the client floor, for QA / escalation tuning.
BACKEND_STREAM_LOW_CONFIDENCE_EVENT = "voice.backend.stream.low_confidence"
# TASK-WEB-045 (BUG-018 fix #1): the whole streamed turn is bounded by an overall wall-clock
# deadline in addition to the per-read socket timeout, so a backend that trickles bytes but never
# emits a terminal done/error cannot hold the turn open. Hitting it aborts the stream and degrades
# to the safe fallback — already-spoken sentences are kept, never un-said (DEC-002) — and records
# this event (elapsed + where in the turn it fired).
BACKEND_STREAM_DEADLINE_EVENT = "voice.turn.deadline_exceeded"

_SENTINEL = object()

PushSentence = Callable[[str], Awaitable[None]]


class _StreamState:
    """Mutable accumulator for one streamed turn (kept tiny + private)."""

    def __init__(self) -> None:
        self.sentence_count = 0
        self.first_ms: float | None = None
        self.confidence: float | None = None
        self.grounded: bool | None = None
        self.done_text: str | None = None
        self.done_seen = False
        self.error_code: str | None = None
        self.error_reason: str | None = None
        self.deadline_exceeded = False
        self._voiced: list[str] = []

    def add_sentence(self, text: str, first_ms: float) -> None:
        if self.sentence_count == 0:
            self.first_ms = first_ms
        self.sentence_count += 1
        self._voiced.append(text)

    def voiced_text(self) -> str:
        return self.done_text if self.done_text else " ".join(self._voiced)


class StreamedAnswerRunner:
    """Drives one `answer_stream` turn: push each vetted sentence, map the outcome."""

    def __init__(
        self,
        backend: Any,
        telemetry: Any,
        *,
        confidence_threshold: float,
        provider: str | None = None,
        deadline_ms: float | None = None,
    ) -> None:
        self._backend = backend
        self._telemetry = telemetry
        self._confidence_threshold = confidence_threshold
        self._provider = provider or getattr(backend, "name", "backend")
        self._deadline_ms = deadline_ms

    async def run(self, request: AnswerRequest, push: PushSentence) -> AnswerResult:
        control = StreamControl()
        timer = Timer()
        state = _StreamState()
        iterator = self._backend.answer_stream(request, control)
        try:
            await self._consume_bounded(iterator, push, state, timer)
        except asyncio.CancelledError:
            control.abort()
            self._emit_interrupted(request, state, timer.elapsed_ms())
            raise
        except EmptyTranscriptError:
            # Nothing to answer: never invent a turn and never speak — mirror the blocking
            # path so the caller stays silent (no fallback, no degraded telemetry).
            control.abort()
            raise
        except asyncio.TimeoutError:
            # TASK-WEB-045: the overall wall-clock deadline fired mid-turn (a live-but-never-
            # terminating stream). Abort the read (closes the socket so the blocked next()
            # unblocks) and degrade to the safe fallback via _finalize; any sentence already
            # spoken is kept, never un-said (DEC-002).
            control.abort()
            state.deadline_exceeded = True
        except Exception as exc:  # noqa: BLE001 - a raising adapter degrades safely, never crashes the turn
            control.abort()
            state.error_code = state.error_code or "stream_error"
            state.error_reason = state.error_reason or type(exc).__name__
        finally:
            control.abort()
        result = self._finalize(request, state)
        if state.sentence_count == 0:
            # Nothing was streamed/spoken (empty stream or an error before any chunk):
            # speak the safe fallback so the caller always hears something.
            await push(result.text)
        self._emit_telemetry(request, result, state, timer.elapsed_ms())
        return result

    async def _consume_bounded(self, iterator: Any, push: PushSentence, state: _StreamState, timer: Timer) -> None:
        # TASK-WEB-045: bound the whole turn by an overall wall-clock deadline (in addition to the
        # per-read socket timeout). <= 0 / None disables it (per-read timeout only). asyncio.wait_for
        # cancels the inner consume on timeout, surfacing as TimeoutError to run().
        if self._deadline_ms is not None and self._deadline_ms > 0:
            await asyncio.wait_for(self._consume(iterator, push, state, timer), timeout=self._deadline_ms / 1000.0)
        else:
            await self._consume(iterator, push, state, timer)

    async def _consume(self, iterator: Any, push: PushSentence, state: _StreamState, timer: Timer) -> None:
        while True:
            event = await asyncio.to_thread(next, iterator, _SENTINEL)
            if event is _SENTINEL:
                return
            await self._handle(event, push, state, timer)

    async def _handle(self, event: Any, push: PushSentence, state: _StreamState, timer: Timer) -> None:
        if event.kind == CHUNK and event.text:
            state.add_sentence(event.text, timer.elapsed_ms())
            await push(event.text)
        elif event.kind == DONE:
            state.done_seen = True
            state.done_text = event.text
            state.confidence = event.confidence
            state.grounded = event.grounded
        elif event.kind == ERROR:
            state.error_code = event.error_code
            state.error_reason = event.error_reason

    def _finalize(self, request: AnswerRequest, state: _StreamState) -> AnswerResult:
        if state.error_code is not None:
            return degraded_answer(
                request,
                provider=self._provider,
                degraded_reason=BACKEND_UNAVAILABLE_REASON,
                confidence=state.confidence,
                error_code=state.error_code,
                error_reason=state.error_reason,
            )
        if state.sentence_count == 0:
            return degraded_answer(
                request, provider=self._provider, degraded_reason=EMPTY_ANSWER_REASON, confidence=state.confidence
            )
        # SUCCESS only when the backend confirmed a grounded answer with a terminal `done`.
        # A non-grounded `done` (guardrail block / low-confidence hand-off) or a truncated
        # stream (sentences but no `done`/`error`, e.g. a dropped connection) both degrade:
        # the vetted sentences already spoken stay the result text (never re-fabricated).
        grounded_complete = state.done_seen and state.grounded is not False
        outcome = AnswerOutcome.SUCCESS if grounded_complete else AnswerOutcome.DEGRADED
        reason = None if outcome is AnswerOutcome.SUCCESS else (
            LOW_CONFIDENCE_REASON if state.done_seen else BACKEND_UNAVAILABLE_REASON
        )
        return AnswerResult(
            text=state.voiced_text(),
            provider=self._provider,
            outcome=outcome,
            correlation_id=request.correlation_id,
            confidence=state.confidence,
            degraded_reason=reason,
        )

    def _emit_telemetry(
        self, request: AnswerRequest, result: AnswerResult, state: _StreamState, total_ms: float
    ) -> None:
        if self._telemetry is None:
            return
        attrs = self._attrs(request, result, state)
        if state.first_ms is not None:
            self._telemetry.span(BACKEND_FIRST_TOKEN_SPAN, state.first_ms, **attrs)
        self._telemetry.span(BACKEND_REQUEST_SPAN, total_ms, **attrs)
        self._telemetry.record(BACKEND_STREAMED_EVENT, backend_request_ms=round(total_ms, 3), **attrs)
        if result.outcome is AnswerOutcome.DEGRADED:
            self._telemetry.log("warning", "backend streamed degraded fallback served", **attrs)
        if state.deadline_exceeded:
            # TASK-WEB-045: make the wall-clock deadline hit observable (elapsed + sentences =
            # where in the turn it fired) so a live-but-stuck backend is visible next time.
            self._telemetry.record(
                BACKEND_STREAM_DEADLINE_EVENT,
                elapsed_ms=round(total_ms, 3),
                deadline_ms=self._deadline_ms,
                **attrs,
            )
        self._maybe_log_low_confidence(result, attrs)

    def _maybe_log_low_confidence(self, result: AnswerResult, attrs: dict[str, Any]) -> None:
        # Option A: a grounded SUCCESS answer below the floor stays spoken (backend grounding
        # already gates DEC-002); record it as advisory only, never as a downgrade.
        if (
            result.outcome is AnswerOutcome.SUCCESS
            and result.confidence is not None
            and result.confidence < self._confidence_threshold
        ):
            self._telemetry.record(BACKEND_STREAM_LOW_CONFIDENCE_EVENT, **attrs)

    def _emit_interrupted(self, request: AnswerRequest, state: _StreamState, total_ms: float) -> None:
        if self._telemetry is None:
            return
        self._telemetry.record(
            BACKEND_STREAM_INTERRUPTED_EVENT,
            correlation_id=request.correlation_id,
            channel=request.channel,
            provider=self._provider,
            outcome="interrupted",
            sentences=state.sentence_count,
            elapsed_ms=round(total_ms, 3),
        )

    def _attrs(self, request: AnswerRequest, result: AnswerResult, state: _StreamState) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "correlation_id": request.correlation_id,
            "channel": request.channel,
            "provider": result.provider or self._provider,
            "outcome": result.outcome.value,
            "answer_chars": len(result.text),
            "sentences": state.sentence_count,
            "degraded": result.outcome is AnswerOutcome.DEGRADED,
        }
        if result.confidence is not None:
            attrs["confidence"] = round(result.confidence, 4)
        if result.degraded_reason:
            attrs["degraded_reason"] = result.degraded_reason
        if result.error_code:
            attrs["error_code"] = result.error_code
        if result.error_reason:
            attrs["error_reason"] = result.error_reason
        return attrs
