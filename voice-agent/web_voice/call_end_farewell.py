"""End-of-call farewell processor for the streaming voice loop (TASK-WEB-010, ADR-0035).

Sits between STT and the answer step. On a customer *closing* formula it does not answer;
it speaks a confirmation question ("Souhaitez-vous autre chose ?") and waits. It ends the
call only when the customer confirms they are done **or** stays silent for a bounded
window; any other utterance cancels the farewell and is answered normally.

The bot speaks by pushing a plain `TextFrame` (the downstream TTS stage synthesises plain
`TextFrame`s; `TranscriptionFrame` subclasses are forwarded untouched). Ending the call is
delegated to an injected `end_call(signal)` callback so this processor stays
transport-agnostic and unit-testable; the WebRTC signaling wires it to the TASK-WEB-008
drain path and the end-of-call reason telemetry.
"""

import asyncio
from enum import Enum, auto
from typing import Any, Awaitable, Callable

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from .closing_intent import ClosingIntentDetector

DEFAULT_CONFIRM_PROMPT = "Souhaitez-vous autre chose ?"
DEFAULT_CLOSING_MESSAGE = "Merci de votre appel. Bonne journée, au revoir !"
# Bounded confirmation-scoped silence window (ADR-0035 point 3). NOT a general mid-call
# silence-timeout (OQ-041-c, out of scope): armed only while awaiting the confirmation.
DEFAULT_CONFIRM_TIMEOUT_S = 6.0

SIGNAL_CONFIRMATION = "confirmation"
SIGNAL_SILENCE = "silence"

EndCallCallback = Callable[[str], Awaitable[None]]


class _State(Enum):
    IDLE = auto()
    AWAITING_CONFIRMATION = auto()


class CallEndFarewellProcessor(FrameProcessor):
    """`TranscriptionFrame` -> detect closing -> confirm -> speak closing -> end call."""

    def __init__(
        self,
        detector: ClosingIntentDetector,
        envelope: Any,
        telemetry: Any = None,
        *,
        confirm_prompt: str = DEFAULT_CONFIRM_PROMPT,
        closing_message: str = DEFAULT_CLOSING_MESSAGE,
        confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
        end_call: EndCallCallback | None = None,
    ) -> None:
        super().__init__()
        self._detector = detector
        self._envelope = envelope
        self._telemetry = telemetry
        self._confirm_prompt = confirm_prompt
        self._closing_message = closing_message
        self._confirm_timeout_s = confirm_timeout_s
        self._end_call = end_call
        self._state = _State.IDLE
        self._timer: asyncio.Task | None = None
        # Read by tests: the last end signal emitted (confirmation / silence), or None.
        self.last_end_signal: str | None = None

    def set_end_call(self, end_call: EndCallCallback) -> None:
        """Wire the teardown callback after construction (the session/connection that it
        drains does not exist yet when the processor is built)."""
        self._end_call = end_call

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, (EndFrame, CancelFrame)):
            self._cancel_timer()
            await self.push_frame(frame, direction)
        elif isinstance(frame, TranscriptionFrame):
            await self._on_transcript(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _on_transcript(self, frame: TranscriptionFrame, direction: FrameDirection) -> None:
        if self._state is _State.AWAITING_CONFIRMATION:
            await self._handle_confirmation(frame, direction)
        else:
            await self._handle_idle(frame, direction)

    async def _handle_idle(self, frame: TranscriptionFrame, direction: FrameDirection) -> None:
        decision = self._detector.detect_closing(frame.text)
        if not decision.is_closing:
            await self.push_frame(frame, direction)  # normal answer path
            return
        self._record("voice.call_end.closing_detected", matched_phrase=decision.matched_phrase)
        self._state = _State.AWAITING_CONFIRMATION
        # Speak the confirmation and suppress the answer (do not forward the transcript).
        await self.push_frame(TextFrame(text=self._confirm_prompt), direction)
        self._arm_timer(direction)

    async def _handle_confirmation(self, frame: TranscriptionFrame, direction: FrameDirection) -> None:
        self._cancel_timer()
        self._state = _State.IDLE
        if self._confirms_done(frame.text):
            await self._end_call_with(SIGNAL_CONFIRMATION, direction)
        else:
            # The customer wants something else: cancel the farewell, answer normally.
            self._record("voice.call_end.cancelled")
            await self.push_frame(frame, direction)

    def _confirms_done(self, text: str) -> bool:
        """The confirmation answer ends the call when it is an explicit "done" ("non",
        "c'est tout") OR a repeated standalone closing ("non, au revoir" / "au revoir"),
        so re-saying goodbye is not mistaken for a new request."""
        return self._detector.is_done_confirmation(text) or self._detector.detect_closing(text).is_closing

    def _arm_timer(self, direction: FrameDirection) -> None:
        self._cancel_timer()
        self._timer = asyncio.get_running_loop().create_task(self._on_silence(direction))

    def _cancel_timer(self) -> None:
        if self._timer is not None and not self._timer.done():
            self._timer.cancel()
        self._timer = None

    async def _on_silence(self, direction: FrameDirection) -> None:
        try:
            await asyncio.sleep(self._confirm_timeout_s)
        except asyncio.CancelledError:
            return
        # No answer within the window while still awaiting: silence == done.
        if self._state is _State.AWAITING_CONFIRMATION:
            self._state = _State.IDLE
            await self._end_call_with(SIGNAL_SILENCE, direction)

    async def _end_call_with(self, signal: str, direction: FrameDirection) -> None:
        self.last_end_signal = signal
        self._record("voice.call_end.confirmed", signal=signal)
        # Speak the closing, then hand off to the teardown callback (which drains the
        # closing audio through the TASK-WEB-008 path before ending the session).
        await self.push_frame(TextFrame(text=self._closing_message), direction)
        if self._end_call is not None:
            await self._end_call(signal)

    def _record(self, name: str, **attributes: Any) -> None:
        if self._telemetry is None or self._envelope is None:
            return
        clean = {key: value for key, value in attributes.items() if value is not None}
        self._telemetry.record(name, correlation_id=self._envelope.correlation_id, **clean)
