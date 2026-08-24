"""Transport-agnostic control-signal processor (TASK-WEB-029, ADR-0043/0040).

Front-of-pipeline seam that turns pluggable `ControlSignal`s into the pipeline actions the
session core already understands, and emits Genesys-named control telemetry. With no source
injected it is a **transparent pass-through** (the energy detectors inside
`StreamingSttProcessor` stay authoritative); a fake / Genesys / WS-client source can drive
barge-in and end-of-turn **without** the energy detector — the pluggability the ADR calls for.

Mapping:
- `barge_in`   -> `broadcast_interruption()` (Pipecat cancels the in-flight streaming TTS and
                  the output transport flushes its audio; playback stops promptly).
- `end_of_turn`-> push `EndOfTurnSignalFrame` downstream (STT finalizes the open turn now).
- `call_end`   -> injected `end_call(signal)` if wired, else a graceful `EndFrame`.
- playback lifecycle -> Genesys-named telemetry from the transport's Bot(Started|Stopped)Speaking.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    Frame,
    StartFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from .control_signals import (
    ControlSignal,
    ControlSignalSource,
    ControlSignalType,
    EndOfTurnSignalFrame,
)

CONTROL_SIGNAL_EVENT = "voice.control_signal"

_logger = logging.getLogger(__name__)

EndCallCallback = Callable[[str], Awaitable[None]]


class ControlSignalProcessor(FrameProcessor):
    """Pluggable control-signal entry point in front of the STT stage."""

    def __init__(
        self,
        *,
        telemetry: Any = None,
        correlation_id: str | None = None,
        source: ControlSignalSource | None = None,
        end_call: EndCallCallback | None = None,
    ) -> None:
        super().__init__()
        self._telemetry = telemetry
        self._correlation_id = correlation_id
        self._source = source
        self._end_call = end_call
        self._task: asyncio.Task | None = None

    def set_end_call(self, end_call: EndCallCallback) -> None:
        """Wire the shared end-of-call teardown (same callback the farewell processor uses)."""
        self._end_call = end_call

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            self._start_source()
        elif isinstance(frame, (EndFrame, CancelFrame)):
            await self._stop_source()
        elif isinstance(frame, BotStartedSpeakingFrame):
            self._record(ControlSignalType.PLAYBACK_STARTED)
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._record(ControlSignalType.PLAYBACK_COMPLETED)
        await self.push_frame(frame, direction)

    def _start_source(self) -> None:
        if self._source is not None and self._task is None:
            self._task = asyncio.create_task(self._consume())

    async def _stop_source(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 - a faulty source must not break teardown
                # Surface it (a source dying silently would hide a control-plane outage) but
                # never let it break the session teardown.
                _logger.warning("control-signal source failed", exc_info=True)
            self._task = None
        if self._source is not None:
            await self._source.close()

    async def _consume(self) -> None:
        async for signal in self._source.signals():
            await self.dispatch(signal)

    async def dispatch(self, signal: ControlSignal) -> None:
        """Map one control signal to a pipeline action (also the unit-test entry point)."""
        self._record(signal.type)
        if signal.type is ControlSignalType.BARGE_IN:
            await self.broadcast_interruption()
        elif signal.type is ControlSignalType.END_OF_TURN:
            await self.push_frame(EndOfTurnSignalFrame(), FrameDirection.DOWNSTREAM)
        elif signal.type is ControlSignalType.CALL_END:
            await self._dispatch_call_end()

    async def _dispatch_call_end(self) -> None:
        if self._end_call is not None:
            await self._end_call(ControlSignalType.CALL_END.value)
        else:
            await self.push_frame(EndFrame(), FrameDirection.DOWNSTREAM)

    def _record(self, signal_type: ControlSignalType) -> None:
        if self._telemetry is None:
            return
        self._telemetry.record(
            CONTROL_SIGNAL_EVENT,
            correlation_id=self._correlation_id,
            signal=signal_type.value,
        )
