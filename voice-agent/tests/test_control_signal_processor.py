"""Tests for the pluggable control-signal processor (TASK-WEB-029, ADR-0043/0040).

Covers the two AC seams and the Genesys-named vocabulary:
- `dispatch()` maps each control signal to the right pipeline action (barge-in ->
  `broadcast_interruption`, end-of-turn -> `EndOfTurnSignalFrame` downstream, call-end ->
  injected `end_call` or a graceful `EndFrame`), and records `voice.control_signal` telemetry
  named after Genesys semantics;
- an injected `ControlSignalSource` drives those actions through a running pipeline **without**
  the energy detector (the pluggability AC), and is closed on teardown;
- with no source the processor is a transparent pass-through (no consumer task, no control
  telemetry), so the energy detectors inside `StreamingSttProcessor` stay authoritative.
"""

import asyncio
import sys
import unittest
import warnings
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from pipecat.frames.frames import (  # noqa: E402
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    EndFrame,
    Frame,
    InterruptionFrame,
    StartFrame,
    TextFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402

from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice.control_signal_processor import (  # noqa: E402
    CONTROL_SIGNAL_EVENT,
    ControlSignalProcessor,
)
from web_voice.control_signals import (  # noqa: E402
    ControlSignal,
    ControlSignalSource,
    ControlSignalType,
    EndOfTurnSignalFrame,
)


class _ScriptedSource(ControlSignalSource):
    """Yields scripted control signals (with a tiny gap) then completes; records close()."""

    def __init__(self, signals):
        self._signals = list(signals)
        self.closed = False

    async def signals(self):
        for signal in self._signals:
            yield signal
            await asyncio.sleep(0.01)

    async def close(self) -> None:
        self.closed = True


class _Passthrough(FrameProcessor):
    def __init__(self, forward=None) -> None:
        super().__init__()
        self._forward = forward or []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            for extra in self._forward:
                await self.push_frame(extra, FrameDirection.DOWNSTREAM)


class _Sink(FrameProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.interruptions = 0
        self.end_of_turn_signals = 0
        self.texts: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, EndOfTurnSignalFrame):
            self.end_of_turn_signals += 1
        elif isinstance(frame, InterruptionFrame):
            self.interruptions += 1
        elif type(frame) is TextFrame:
            self.texts.append(frame.text)
        await self.push_frame(frame, direction)


async def _run_until(sink: _Sink, predicate, *, source_extra=None, processor=None) -> _Sink:
    pipeline = Pipeline([_Passthrough(source_extra), processor, sink])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask

        task = PipelineTask(
            pipeline, params=PipelineParams(), enable_rtvi=False,
            enable_turn_tracking=False, cancel_on_idle_timeout=False, check_dangling_tasks=False,
        )
        run = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        deadline = asyncio.get_event_loop().time() + 1.5
        while not predicate() and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink


class ControlSignalDispatchTest(unittest.IsolatedAsyncioTestCase):
    """dispatch() maps a signal to a pipeline action — patched, no running pipeline."""

    def _patched(self, telemetry=None, end_call=None):
        processor = ControlSignalProcessor(
            telemetry=telemetry, correlation_id="corr-1", end_call=end_call
        )
        pushed: list[Frame] = []
        broadcasts = {"count": 0}

        async def _fake_push(frame, direction=FrameDirection.DOWNSTREAM):
            pushed.append(frame)

        async def _fake_broadcast():
            broadcasts["count"] += 1

        processor.push_frame = _fake_push  # type: ignore[assignment]
        processor.broadcast_interruption = _fake_broadcast  # type: ignore[assignment]
        return processor, pushed, broadcasts

    async def test_barge_in_broadcasts_interruption(self):
        # GIVEN a control processor
        processor, pushed, broadcasts = self._patched()
        # WHEN a barge_in signal is dispatched
        await processor.dispatch(ControlSignal(ControlSignalType.BARGE_IN))
        # THEN it broadcasts one interruption and pushes no frame
        self.assertEqual(broadcasts["count"], 1)
        self.assertEqual(pushed, [])

    async def test_end_of_turn_pushes_signal_frame_downstream(self):
        # GIVEN a control processor
        processor, pushed, _ = self._patched()
        # WHEN an end_of_turn signal is dispatched
        await processor.dispatch(ControlSignal(ControlSignalType.END_OF_TURN))
        # THEN one EndOfTurnSignalFrame is pushed downstream
        self.assertEqual(len(pushed), 1)
        self.assertIsInstance(pushed[0], EndOfTurnSignalFrame)

    async def test_call_end_pushes_end_frame_when_no_callback(self):
        # GIVEN a control processor with no end_call wired
        processor, pushed, _ = self._patched()
        # WHEN a call_end signal is dispatched
        await processor.dispatch(ControlSignal(ControlSignalType.CALL_END))
        # THEN it falls back to a graceful EndFrame
        self.assertEqual(len(pushed), 1)
        self.assertIsInstance(pushed[0], EndFrame)

    async def test_call_end_uses_injected_end_call(self):
        # GIVEN an injected end-of-call callback (same seam the farewell processor uses)
        calls: list[str] = []

        async def _end_call(signal: str) -> None:
            calls.append(signal)

        processor, pushed, _ = self._patched(end_call=_end_call)
        # WHEN a call_end signal is dispatched
        await processor.dispatch(ControlSignal(ControlSignalType.CALL_END))
        # THEN the callback runs with the Genesys-named reason and no EndFrame is pushed
        self.assertEqual(calls, ["call_end"])
        self.assertEqual(pushed, [])

    async def test_records_genesys_named_control_telemetry(self):
        # GIVEN telemetry wiring
        telemetry = TelemetryRecorder()
        processor, _, _ = self._patched(telemetry=telemetry)
        # WHEN each control signal is dispatched
        for signal_type in (ControlSignalType.BARGE_IN, ControlSignalType.END_OF_TURN):
            await processor.dispatch(ControlSignal(signal_type))
        # THEN each is recorded as a voice.control_signal event with the Genesys-named signal
        events = [e for e in telemetry.events() if e.name == CONTROL_SIGNAL_EVENT]
        self.assertEqual([e.attributes["signal"] for e in events], ["barge_in", "end_of_turn"])
        self.assertTrue(all(e.attributes["correlation_id"] == "corr-1" for e in events))


class ControlSignalSourceTest(unittest.IsolatedAsyncioTestCase):
    """An injected source drives actions through a running pipeline (pluggability AC)."""

    async def test_source_end_of_turn_reaches_pipeline_and_source_closed(self):
        # GIVEN a processor fed by a source that emits one end_of_turn (no energy detector)
        source = _ScriptedSource([ControlSignal(ControlSignalType.END_OF_TURN)])
        processor = ControlSignalProcessor(source=source, correlation_id="corr-1")
        sink = _Sink()
        # WHEN the pipeline runs
        await _run_until(sink, lambda: sink.end_of_turn_signals >= 1, processor=processor)
        # THEN an EndOfTurnSignalFrame reached the sink and the source was closed on teardown
        self.assertEqual(sink.end_of_turn_signals, 1)
        self.assertTrue(source.closed)

    async def test_source_barge_in_broadcasts_interruption_through_pipeline(self):
        # GIVEN a processor fed by a source that emits one barge_in
        source = _ScriptedSource([ControlSignal(ControlSignalType.BARGE_IN)])
        processor = ControlSignalProcessor(source=source, correlation_id="corr-1")
        sink = _Sink()
        # WHEN the pipeline runs
        await _run_until(sink, lambda: sink.interruptions >= 1, processor=processor)
        # THEN a broadcast InterruptionFrame reached the sink
        self.assertGreaterEqual(sink.interruptions, 1)


class ControlSignalPassthroughTest(unittest.IsolatedAsyncioTestCase):
    async def test_playback_frames_emit_genesys_named_telemetry(self):
        # GIVEN a processor with telemetry and no source
        telemetry = TelemetryRecorder()
        processor = ControlSignalProcessor(telemetry=telemetry, correlation_id="corr-1")
        sink = _Sink()
        playback = [BotStartedSpeakingFrame(), BotStoppedSpeakingFrame()]
        # WHEN the transport's playback-lifecycle frames flow through
        await _run_until(
            sink,
            lambda: len([e for e in telemetry.events() if e.name == CONTROL_SIGNAL_EVENT]) >= 2,
            source_extra=playback,
            processor=processor,
        )
        # THEN they are recorded with the Genesys-named playback vocabulary
        signals = [e.attributes["signal"] for e in telemetry.events() if e.name == CONTROL_SIGNAL_EVENT]
        self.assertIn("playback_started", signals)
        self.assertIn("playback_completed", signals)

    async def test_transparent_passthrough_without_source(self):
        # GIVEN a processor with telemetry but no source
        telemetry = TelemetryRecorder()
        processor = ControlSignalProcessor(telemetry=telemetry, correlation_id="corr-1")
        sink = _Sink()
        # WHEN a plain answer TextFrame flows through
        await _run_until(sink, lambda: bool(sink.texts), source_extra=[TextFrame(text="bonjour")], processor=processor)
        # THEN it is forwarded untouched and no control-signal telemetry is emitted (no consumer task)
        self.assertEqual(sink.texts, ["bonjour"])
        self.assertEqual([e for e in telemetry.events() if e.name == CONTROL_SIGNAL_EVENT], [])


if __name__ == "__main__":
    unittest.main()
