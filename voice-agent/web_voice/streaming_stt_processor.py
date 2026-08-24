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
from uuid import uuid4

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from .session_warmer import ACQUIRE_HIT, SessionWarmer

from conversation_backend import DEGRADED_FALLBACK_TEXT
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
    _pcm16_samples,
    _peak_amplitude,
)

DEFAULT_PROVIDER_NAME = "gradium-stt-streaming"
STT_REQUEST_SPAN = "stt.request"
# TASK-WEB-018: when streaming STT finalize fails (timeout / provider error), the loop
# must not go silent — it speaks the safe degraded fallback (same policy as the batch
# path and the backend degraded mode). This event proves a fallback was actually driven
# to TTS so QA can distinguish "spoke a safe fallback" from "silent call".
STT_DEGRADED_SPOKEN_EVENT = "voice.stt.degraded_spoken"
STT_DEGRADED_SPOKEN_METRIC = "voice.stt.degraded_spoken.count"
STT_DEGRADED_REASON = "stt_finalize_failed"
# Streaming-STT partial-semantics drift (TASK-WEB-033): delta partials are live-validated
# (STT-013); this signal fires if a session counted partials that looked cumulative, so a
# provider protocol drift (which append+join would silently duplicate) is observable before it
# corrupts a transcript. Signal only — the session never mutates its validated delta behavior.
STT_PARTIAL_DRIFT_EVENT = "voice.stt.partial_semantics_drift"
STT_PARTIAL_DRIFT_METRIC = "voice.stt.partial_semantics_drift.count"
# Barge-in observability (TASK-WEB-008): emitted when speech onset while the bot is
# speaking triggers an interruption of the spoken answer.
BARGE_IN_EVENT = "voice.barge_in.detected"
BARGE_IN_METRIC = "voice.barge_in.count"
# Connect-time STT pre-warm observability (TASK-WEB-021 lever 2): emitted at the first
# turn's session open so QA can tell a pre-warm hit (spare reused, connect+setup off the
# turn path) from a fallback (spare open failed -> fresh on-demand open) without inferring
# it from slice timing. A spare that opened but was closed by the server while idle still
# reports "hit" here but then fails on send/finalize -> surfaces as the existing
# stt.failure + degraded fallback, so a stale spare is never silent.
STT_PREWARM_EVENT = "voice.stt.prewarm"
STT_PREWARM_METRIC = "voice.stt.prewarm.count"
# Anti-echo barge-in gate (TASK-WEB-008). Without headphones the bot's own audio
# re-enters the mic even with browser echo cancellation, and an energy VAD reads it as
# speech -> the bot self-interrupts. To cut the bot only on a *real* customer barge-in,
# the incoming frame must (1) exceed a HIGHER amplitude than normal speech onset
# (residual echo is attenuated by AEC, so it sits below direct-voice level) AND (2) stay
# above it for several consecutive frames (rejects brief spikes). Both are tunable via
# env in the signaling wiring so the threshold can be raised on echoey speaker setups
# without a code change. The onset threshold (opening the STT session) is unchanged.
DEFAULT_BARGE_IN_AMPLITUDE_THRESHOLD = 2500
DEFAULT_BARGE_IN_CONFIRM_FRAMES = 4
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
        silence_window_ms: float = DEFAULT_SILENCE_WINDOW_MS,
        final_timeout_s: float = DEFAULT_FINAL_TIMEOUT_S,
        barge_in_amplitude_threshold: int = DEFAULT_BARGE_IN_AMPLITUDE_THRESHOLD,
        barge_in_confirm_frames: int = DEFAULT_BARGE_IN_CONFIRM_FRAMES,
        prewarm: bool = True,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._envelope = envelope
        self._telemetry = telemetry
        self._provider_name = provider_name
        self._final_timeout_s = final_timeout_s
        # TASK-WEB-021 lever 2: pre-open the first turn's STT session at pipeline start so
        # its connect + setup handshake is off the per-turn critical path. Gradium's ASR
        # socket is single-use, so we pre-open a *spare* (not reuse); the spare is handed
        # out on the first `_open_session` and any unused spare is discarded at teardown
        # so a pre-warmed connection is never leaked. Tests opt out to assert the raw path.
        self._prewarm = prewarm
        self._warmer = SessionWarmer(provider)
        self._barge_in_amplitude_threshold = barge_in_amplitude_threshold
        self._barge_in_confirm_frames = max(1, barge_in_confirm_frames)
        # TASK-WEB-015 lever 3: the trailing-silence hold is env-tunable (via the
        # signaling wiring) so a deployment can trade ~150 ms of latency against the
        # premature-cut risk without a code change. An injected detector still wins.
        self._detector = detector or StreamingEndOfTurnDetector(
            sample_rate_hz=sample_rate_hz,
            silence_window_ms=silence_window_ms,
            amplitude_threshold=DEFAULT_AMPLITUDE_THRESHOLD,
            min_utterance_ms=DEFAULT_MIN_UTTERANCE_MS,
        )
        self._user_id = getattr(envelope, "external_session_id", "") or "web"
        self._session: Any = None
        self._turn_timer: Timer | None = None
        self._first_partial_ms: float | None = None
        # Monotonic per-turn index on this streaming session (TASK-WEB-017). One recorder
        # lives for the whole call, so we advance a fresh per-turn identity at each
        # end-of-turn while the per-conversation correlation_id stays stable; all spans
        # of the turn (STT, backend, TTS, egress) then carry it via the recorder baggage.
        self._turn_index = 0
        # Read by tests: number of final transcripts emitted this session.
        self.final_count = 0
        # True while the bot's spoken answer is playing (tracked from the
        # BotStarted/StoppedSpeakingFrame the output transport emits upstream). Speech
        # onset is treated as a barge-in only while this is set (TASK-WEB-008).
        self._bot_speaking = False
        # Consecutive above-threshold frames seen while the bot speaks; barge-in fires
        # once the count reaches _barge_in_confirm_frames (anti-echo gate). Reset when a
        # frame drops below threshold, when the bot (re)starts speaking, or after firing.
        self._barge_in_confirm_count = 0
        # Fires the cut at most once per bot-speaking span; reset on BotStartedSpeaking.
        self._barge_in_fired = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            await self._on_audio(frame, direction)
        elif isinstance(frame, StartFrame):
            # Pre-open the first turn's STT session at pipeline start (TASK-WEB-021).
            if self._prewarm:
                self._warmer.start()
            await self.push_frame(frame, direction)
        elif isinstance(frame, EndFrame):
            await self._on_end(direction)
            await self._warmer.aclose()
            await self.push_frame(frame, direction)
        elif isinstance(frame, CancelFrame):
            # Cancelled call: drop any unused spare so a pre-warmed socket is never leaked.
            await self._warmer.aclose()
            await self.push_frame(frame, direction)
        elif isinstance(frame, (BotStartedSpeakingFrame, BotStoppedSpeakingFrame)):
            # The output transport emits these upstream as it starts / stops playing the
            # bot audio; track the state and forward them untouched. Reset the anti-echo
            # confirmation gate on every transition so a new answer starts clean.
            self._bot_speaking = isinstance(frame, BotStartedSpeakingFrame)
            self._barge_in_confirm_count = 0
            self._barge_in_fired = False
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _on_audio(self, frame: InputAudioRawFrame, direction: FrameDirection) -> None:
        decision = self._detector.observe(frame.audio)
        if self._detector.has_speech and self._session is None:
            await self._open_session()
        if self._bot_speaking and not self._barge_in_fired:
            await self._maybe_barge_in(frame.audio)
        if self._session is not None:
            await self._session.send_audio(frame.audio)
            await self._emit_partials(self._session, direction)
        if decision.detection is not None:
            await self._finalize(decision.detection, direction)
        elif decision.discard:
            await self._discard_session()

    async def _maybe_barge_in(self, audio: bytes) -> None:
        """Anti-echo gate: cut the bot only after a loud-enough, *sustained* onset.

        Residual echo (the bot's own audio leaking back through the mic even with
        browser echo cancellation) is attenuated, so it sits below the barge-in
        amplitude threshold; a real customer speaking close to the mic clears it. The
        N-frame confirmation additionally rejects brief spikes. Only then do we cut.
        """
        peak = _peak_amplitude(_pcm16_samples(audio))
        if peak < self._barge_in_amplitude_threshold:
            self._barge_in_confirm_count = 0
            return
        self._barge_in_confirm_count += 1
        if self._barge_in_confirm_count >= self._barge_in_confirm_frames:
            await self._trigger_barge_in()

    async def _trigger_barge_in(self) -> None:
        """Customer confirmed speaking mid-answer: cut the bot now.

        `broadcast_interruption()` sends an `InterruptionFrame` downstream (Pipecat
        cancels the streaming TTS task and the output transport flushes its buffered
        audio) and upstream, so playback stops promptly. Fires at most once per
        bot-speaking span — `_barge_in_fired` guards re-entry — and clears `_bot_speaking`
        so a stale value cannot re-trigger before the BotStoppedSpeakingFrame arrives.
        """
        self._barge_in_fired = True
        self._bot_speaking = False
        self._barge_in_confirm_count = 0
        self._emit_barge_in()
        await self.broadcast_interruption()

    async def _on_end(self, direction: FrameDirection) -> None:
        decision = self._detector.finish()
        if decision.detection is not None:
            await self._finalize(decision.detection, direction)
        else:
            await self._discard_session()

    async def _open_session(self) -> None:
        # With pre-warm, hand out the spare opened at StartFrame (its connect+setup is
        # already paid); otherwise open on demand. `acquire()` falls back to a fresh open
        # if the spare's open failed, so a cold/failed spare never blocks the turn.
        if self._prewarm:
            self._session = await self._warmer.acquire()
            self._emit_prewarm_outcome(self._warmer.last_acquire)
        else:
            self._session = await self._provider.open()
        self._turn_timer = Timer()
        self._first_partial_ms = None

    def _emit_prewarm_outcome(self, outcome: str | None) -> None:
        if self._telemetry is None or self._envelope is None or outcome is None:
            return
        attrs = {
            "correlation_id": self._envelope.correlation_id,
            "channel": getattr(self._envelope, "channel", None),
            "provider": self._provider_name,
            "outcome": outcome,
        }
        self._telemetry.record(STT_PREWARM_EVENT, prewarm_hit=(outcome == ACQUIRE_HIT), **attrs)
        self._telemetry.metric(STT_PREWARM_METRIC, 1, **attrs)

    async def _emit_partials(self, session: Any, direction: FrameDirection) -> None:
        for partial in session.poll_partials():
            if self._first_partial_ms is None and self._turn_timer is not None:
                self._first_partial_ms = self._turn_timer.elapsed_ms()
            await self.push_frame(
                InterimTranscriptionFrame(text=partial.text, user_id=self._user_id, timestamp=""),
                direction,
            )

    async def _finalize(self, detection: EndOfTurnResult, direction: FrameDirection) -> None:
        self._begin_turn()
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
            await self._speak_degraded_fallback(direction)
            return
        await self._emit_partials(session, direction)
        self._emit_partial_semantics_drift(session)
        await session.aclose()
        await self._emit_final(final, tail.elapsed_ms(), direction)

    def _emit_partial_semantics_drift(self, session: Any) -> None:
        """Surface a streaming-STT partial-semantics drift signal (TASK-WEB-033).

        Delta partials are live-validated (STT-013); if the session counted partials that
        looked cumulative, the provider protocol may have drifted (append+join would then
        duplicate). Emit an observable signal only — the session never mutates its delta
        behavior. Protocol-safe via getattr so a non-Gradium session without the counter
        is a no-op. No transcript is emitted (PII).
        """
        drift = getattr(session, "cumulative_drift_count", 0)
        if not drift or self._telemetry is None or self._envelope is None:
            return
        attrs = {
            "correlation_id": self._envelope.correlation_id,
            "channel": getattr(self._envelope, "channel", None),
            "provider": self._provider_name,
        }
        self._telemetry.record(STT_PARTIAL_DRIFT_EVENT, cumulative_partials=drift, **attrs)
        self._telemetry.metric(STT_PARTIAL_DRIFT_METRIC, drift, **attrs)

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

    async def _speak_degraded_fallback(self, direction: FrameDirection) -> None:
        """Speak the safe degraded fallback when streaming STT finalize fails (TASK-WEB-018).

        Pushes a *plain* `TextFrame` (never a `TranscriptionFrame` — no transcript is
        fabricated) so the downstream TTS stage synthesises the digit/currency-free
        fallback (DEC-002). Without this the streaming path goes silent on an STT
        failure — worse than the batch `/turn` 502. The fallback is a normal bot answer,
        so the output transport emits `BotStartedSpeakingFrame` and barge-in /
        interruption apply unchanged (a customer can still cut the degraded utterance).
        """
        self._emit_degraded_spoken()
        await self.push_frame(TextFrame(text=DEGRADED_FALLBACK_TEXT), direction)

    def _emit_degraded_spoken(self) -> None:
        if self._telemetry is None or self._envelope is None:
            return
        attrs = {
            "correlation_id": self._envelope.correlation_id,
            "channel": getattr(self._envelope, "channel", None),
            "provider": self._provider_name,
            "degraded_reason": STT_DEGRADED_REASON,
        }
        self._telemetry.record(STT_DEGRADED_SPOKEN_EVENT, **attrs)
        self._telemetry.metric(STT_DEGRADED_SPOKEN_METRIC, 1, **attrs)

    def _emit_barge_in(self) -> None:
        if self._telemetry is None or self._envelope is None:
            return
        attrs = {
            "correlation_id": self._envelope.correlation_id,
            "channel": getattr(self._envelope, "channel", None),
            "provider": self._provider_name,
        }
        self._telemetry.record(BARGE_IN_EVENT, **attrs)
        self._telemetry.metric(BARGE_IN_METRIC, 1, **attrs)

    def _begin_turn(self) -> None:
        """Advance the per-turn identity for this call (TASK-WEB-017), keeping the
        per-conversation correlation_id stable. Called first at each end-of-turn so the
        turn's end_of_turn / stt / backend / tts / egress spans all share one turn id."""
        if self._telemetry is None or self._envelope is None:
            return
        self._turn_index += 1
        self._telemetry.begin_turn(
            conversation_id=getattr(self._envelope, "conversation_id", None),
            message_id=str(uuid4()),
            turn_index=self._turn_index,
        )

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
            # Configured hold (TASK-WEB-015 lever 3): lets QA correlate the false-cut
            # rate to the deployed window, even on client_stop turns where slice_ms is
            # the (short) real trailing silence rather than the window.
            "silence_window_ms": self._detector.silence_window_ms,
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
