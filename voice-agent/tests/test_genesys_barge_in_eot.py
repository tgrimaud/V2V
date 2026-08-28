"""Tests for the Genesys Audio Connector barge-in / end-of-turn / call-end ownership
(TASK-WEB-042).

Two levels, both with manual fakes (no Mockito), GIVEN/WHEN/THEN:

- The barge-in + end-of-turn machinery is the SHARED `StreamingSttProcessor` the Genesys
  transport builds through the unchanged `SessionFactory` (ADR-0043). These tests drive PCM
  through it with a **Genesys envelope** and assert the same anti-echo sustained-onset gate
  fires (and rejects echo) and end-of-turn flushes on the silence window, with every span /
  event / metric carrying `channel=genesys_audio_connector` (per-path observability, WEB-043).
- The Genesys-specific wiring in `web_voice.genesys_barge_in_eot`: the native control-signal
  SOURCE seam (idle in `detector` mode, the working default), the control-mode config, and the
  end-of-call reason recorder + drain wiring (idempotent, first-trigger-wins, no PII).
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
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402

from stt_validation.streaming import FinalTranscript, PartialTranscript  # noqa: E402
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice.control_signals import ControlSignal, ControlSignalType  # noqa: E402
from web_voice.end_of_turn import DEFAULT_AMPLITUDE_THRESHOLD, StreamingEndOfTurnDetector  # noqa: E402
from web_voice.envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL, ChannelEnvelope  # noqa: E402
from web_voice.genesys_barge_in_eot import (  # noqa: E402
    CONTROL_MODE_DETECTOR,
    CONTROL_MODE_ENV_VAR,
    CONTROL_MODE_NATIVE,
    GenesysCallControl,
    GenesysControlSignalSource,
    genesys_control_mode_config,
    genesys_control_source_factory,
    wire_genesys_call_control,
)
from web_voice.genesys_cap import DrainOnce  # noqa: E402
from web_voice.genesys_config import (  # noqa: E402
    CALL_END_EVENT,
    REASON_CAP_REACHED,
    REASON_CLIENT_DISCONNECT,
    REASON_CUSTOMER_FAREWELL,
)
from web_voice.streaming_stt_processor import StreamingSttProcessor  # noqa: E402

SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = (SAMPLE_RATE * FRAME_MS // 1000) * 2


# --------------------------------------------------------------------------------------
# Shared-machinery level: barge-in + end-of-turn on the Genesys channel
# --------------------------------------------------------------------------------------
def _genesys_envelope() -> ChannelEnvelope:
    return ChannelEnvelope.for_genesys_turn(conversation_id="genesys-conv-1")


def _detector() -> StreamingEndOfTurnDetector:
    # Fast silence window so a short synthetic clip flushes end-of-turn.
    return StreamingEndOfTurnDetector(
        sample_rate_hz=SAMPLE_RATE,
        silence_window_ms=100,
        amplitude_threshold=DEFAULT_AMPLITUDE_THRESHOLD,
        min_utterance_ms=20.0,
    )


def _processor(provider, telemetry) -> StreamingSttProcessor:
    return StreamingSttProcessor(
        provider, _genesys_envelope(), telemetry, detector=_detector(), prewarm=False
    )


def _pcm_frame(amplitude: int) -> InputAudioRawFrame:
    pcm = amplitude.to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)
    return InputAudioRawFrame(audio=pcm, sample_rate=SAMPLE_RATE, num_channels=1)


def _speech_frame() -> InputAudioRawFrame:
    return _pcm_frame(5000)


def _echo_frame() -> InputAudioRawFrame:
    # Above the onset threshold, below the barge-in threshold: residual echo (TASK-WEB-008).
    return _pcm_frame(1500)


def _silence_frame() -> InputAudioRawFrame:
    return InputAudioRawFrame(audio=b"\x00" * FRAME_BYTES, sample_rate=SAMPLE_RATE, num_channels=1)


class _FakeSession:
    def __init__(self, partials, final_text):
        self._queued = list(partials)
        self._released = []
        self._final_text = final_text
        self.closed = False

    async def send_audio(self, pcm: bytes) -> None:
        if self._queued:
            self._released.append(self._queued.pop(0))

    def poll_partials(self):
        out, self._released = self._released, []
        return out

    async def finish(self) -> None:
        return None

    async def wait_final(self) -> FinalTranscript:
        return FinalTranscript(self._final_text)

    def partial_snapshot(self) -> FinalTranscript:
        return FinalTranscript(self._final_text)

    async def aclose(self) -> None:
        self.closed = True


class _FakeProvider:
    name = "fake-streaming-stt"

    def __init__(self, *sessions):
        self._sessions = list(sessions)
        self.open_count = 0

    async def open(self):
        self.open_count += 1
        return self._sessions.pop(0)


class _Source(FrameProcessor):
    def __init__(self, frames) -> None:
        super().__init__()
        self._frames = frames

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            for f in self._frames:
                await self.push_frame(f, FrameDirection.DOWNSTREAM)


class _Sink(FrameProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.finals: list[str] = []
        self.interruptions = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and not isinstance(
            frame, InterimTranscriptionFrame
        ):
            self.finals.append(frame.text)
        elif isinstance(frame, InterruptionFrame):
            self.interruptions += 1
        await self.push_frame(frame, direction)


async def _drive(processor: StreamingSttProcessor, frames) -> _Sink:
    sink = _Sink()
    pipeline = Pipeline([_Source(frames), processor, sink])
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
        while not sink.finals and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=10)
    return sink


class GenesysBargeInEndOfTurnChannelTest(unittest.IsolatedAsyncioTestCase):
    async def test_barge_in_fires_on_sustained_loud_onset_labelled_genesys(self):
        # GIVEN a Genesys session with the bot speaking, then a sustained loud customer onset
        telemetry = TelemetryRecorder()
        processor = _processor(_FakeProvider(_FakeSession([PartialTranscript("stop")], "stop")), telemetry)
        frames = [BotStartedSpeakingFrame()] + [_speech_frame()] * 6 + [_silence_frame()] * 10
        # WHEN driven through the shared pipeline on the Genesys path
        sink = await _drive(processor, frames)
        # THEN an interruption is broadcast and the barge-in is recorded on the Genesys channel
        self.assertGreaterEqual(sink.interruptions, 1)
        barge = [e for e in telemetry.events() if e.name == "voice.barge_in.detected"]
        self.assertEqual(len(barge), 1)
        self.assertEqual(barge[0].attributes["channel"], GENESYS_AUDIO_CONNECTOR_CHANNEL)
        self.assertTrue(
            any(
                m.name == "voice.barge_in.count"
                and m.attributes["channel"] == GENESYS_AUDIO_CONNECTOR_CHANNEL
                for m in telemetry.metrics()
            )
        )

    async def test_residual_echo_does_not_barge_in_on_genesys(self):
        # GIVEN a Genesys session with the bot speaking and only its own residual echo
        telemetry = TelemetryRecorder()
        processor = _processor(_FakeProvider(_FakeSession([PartialTranscript("echo")], "echo")), telemetry)
        frames = [BotStartedSpeakingFrame()] + [_echo_frame()] * 8 + [_silence_frame()] * 10
        # WHEN driven through the shared pipeline on the Genesys path
        sink = await _drive(processor, frames)
        # THEN the echo never clears the amplitude gate: no interruption, no barge-in
        self.assertEqual(sink.interruptions, 0)
        self.assertFalse(any(e.name == "voice.barge_in.detected" for e in telemetry.events()))

    async def test_end_of_turn_flushes_on_silence_window_labelled_genesys(self):
        # GIVEN a Genesys session with speech followed by a trailing-silence window
        telemetry = TelemetryRecorder()
        processor = _processor(_FakeProvider(_FakeSession([PartialTranscript("bonjour")], "bonjour")), telemetry)
        frames = [_speech_frame()] * 3 + [_silence_frame()] * 10
        # WHEN driven through the shared pipeline on the Genesys path
        sink = await _drive(processor, frames)
        # THEN one final transcript flushes and the end-of-turn span carries the Genesys channel
        self.assertEqual(sink.finals, ["bonjour"])
        eot = [s for s in telemetry.spans() if s.name == "voice.end_of_turn"]
        self.assertEqual(len(eot), 1)
        self.assertEqual(eot[0].attributes["channel"], GENESYS_AUDIO_CONNECTOR_CHANNEL)


# --------------------------------------------------------------------------------------
# Genesys-specific wiring: control-mode config, native seam, call-end reasons
# --------------------------------------------------------------------------------------
class GenesysControlModeConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = self._pop_env()

    def tearDown(self) -> None:
        import os

        os.environ.pop(CONTROL_MODE_ENV_VAR, None)
        if self._saved is not None:
            os.environ[CONTROL_MODE_ENV_VAR] = self._saved

    @staticmethod
    def _pop_env():
        import os

        return os.environ.pop(CONTROL_MODE_ENV_VAR, None)

    def _set(self, value: str) -> None:
        import os

        os.environ[CONTROL_MODE_ENV_VAR] = value

    def test_defaults_to_detector_when_unset(self):
        # GIVEN no env override WHEN resolved THEN the in-house detectors own the path
        self.assertEqual(genesys_control_mode_config(), CONTROL_MODE_DETECTOR)

    def test_native_mode_is_honoured(self):
        # GIVEN the native override WHEN resolved THEN native mode is selected
        self._set("native")
        self.assertEqual(genesys_control_mode_config(), CONTROL_MODE_NATIVE)

    def test_unknown_value_falls_back_to_detector(self):
        # GIVEN a garbage value WHEN resolved THEN it never crashes a call, falls back to detector
        self._set("nonsense")
        self.assertEqual(genesys_control_mode_config(), CONTROL_MODE_DETECTOR)


class GenesysControlSourceFactoryTest(unittest.IsolatedAsyncioTestCase):
    def test_detector_mode_returns_no_factory(self):
        # GIVEN detector mode WHEN the factory is resolved THEN None (detectors stay authoritative)
        self.assertIsNone(genesys_control_source_factory(CONTROL_MODE_DETECTOR))

    def test_native_mode_returns_source_factory(self):
        # GIVEN native mode WHEN the factory is resolved THEN it builds a GenesysControlSignalSource
        factory = genesys_control_source_factory(CONTROL_MODE_NATIVE)
        self.assertIsNotNone(factory)
        source = factory(_genesys_envelope())
        self.assertIsInstance(source, GenesysControlSignalSource)

    async def test_idle_seam_yields_no_signals(self):
        # GIVEN no live AudioHook control stream wired (the preparation default)
        source = GenesysControlSignalSource(_genesys_envelope())
        # WHEN the signals are consumed THEN nothing is produced (detectors stay authoritative)
        collected = [signal async for signal in source.signals()]
        self.assertEqual(collected, [])

    async def test_wired_events_map_via_confirmed_names_only(self):
        # GIVEN a live event stream and a CONFIRMED name mapping (the future live-measurement
        # state, simulated by injecting the map the TODO seam will populate)
        source = GenesysControlSignalSource(
            _genesys_envelope(), events=_aiter([{"type": "barge-in"}, {"type": "unknown"}])
        )
        source._EVENT_TYPE_MAP = {"barge-in": ControlSignalType.BARGE_IN}
        # WHEN the signals are consumed
        collected = [signal async for signal in source.signals()]
        # THEN only confirmed names map to a ControlSignal; unknown names are dropped
        self.assertEqual([s.type for s in collected], [ControlSignalType.BARGE_IN])
        self.assertEqual(collected[0].attributes["source"], "genesys_native")


async def _aiter(items):
    for item in items:
        yield item


class GenesysCallControlTest(unittest.TestCase):
    def _control(self):
        telemetry = TelemetryRecorder()
        return telemetry, GenesysCallControl(telemetry, "genesys-conv-1", DrainOnce())

    def test_records_call_end_once_with_genesys_channel_and_no_pii(self):
        # GIVEN a fresh call-end recorder WHEN a farewell reason is recorded
        telemetry, control = self._control()
        control.record(REASON_CUSTOMER_FAREWELL, signal="confirmation")
        # THEN exactly one voice.call_end event on the Genesys channel, keyed by correlation id
        ends = [e for e in telemetry.events() if e.name == CALL_END_EVENT]
        self.assertEqual(len(ends), 1)
        attrs = ends[0].attributes
        self.assertEqual(attrs["reason"], REASON_CUSTOMER_FAREWELL)
        self.assertEqual(attrs["channel"], GENESYS_AUDIO_CONNECTOR_CHANNEL)
        self.assertEqual(attrs["correlation_id"], "genesys-conv-1")
        # AND no transcript / PII leaks into the attributes (reason + ids + signal only)
        self.assertEqual(
            set(attrs), {"reason", "channel", "correlation_id", "signal"}
        )

    def test_first_reason_wins_farewell_not_overwritten_by_disconnect(self):
        # GIVEN a bot-initiated farewell already recorded
        telemetry, control = self._control()
        control.record(REASON_CUSTOMER_FAREWELL)
        # WHEN the drain-triggered peer disconnect later records its default reason
        control.record_default()
        # THEN the specific farewell reason is preserved (idempotent, first-trigger-wins)
        ends = [e for e in telemetry.events() if e.name == CALL_END_EVENT]
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0].attributes["reason"], REASON_CUSTOMER_FAREWELL)

    def test_on_cap_records_cap_reached(self):
        # GIVEN a call reaching the 15-minute cap WHEN the cap fires
        telemetry, control = self._control()
        control.on_cap()
        # THEN the ending is attributed to the cap, not a generic disconnect
        ends = [e for e in telemetry.events() if e.name == CALL_END_EVENT]
        self.assertEqual([e.attributes["reason"] for e in ends], [REASON_CAP_REACHED])

    def test_record_default_attributes_bare_run_to_client_disconnect(self):
        # GIVEN a call that ended with no farewell/cap WHEN the teardown safety net runs
        telemetry, control = self._control()
        control.record_default()
        # THEN it is honestly attributed to a peer disconnect
        ends = [e for e in telemetry.events() if e.name == CALL_END_EVENT]
        self.assertEqual([e.attributes["reason"] for e in ends], [REASON_CLIENT_DISCONNECT])


class _FakeTransport:
    """Captures the pipecat `on_client_disconnected` handler the wiring registers."""

    def __init__(self):
        self.handlers: dict[str, object] = {}

    def event_handler(self, name: str):
        def _decorator(func):
            self.handlers[name] = func
            return func

        return _decorator


class _FakeDrainSession:
    def __init__(self):
        self.drained = 0

    async def drain(self) -> None:
        self.drained += 1


class _FakeFarewell:
    def __init__(self):
        self.end_call = None

    def set_end_call(self, callback) -> None:
        self.end_call = callback


class WireGenesysCallControlTest(unittest.IsolatedAsyncioTestCase):
    async def test_farewell_confirmation_records_reason_then_drains(self):
        # GIVEN a wired Genesys session with a farewell processor
        telemetry = TelemetryRecorder()
        transport, session, farewell = _FakeTransport(), _FakeDrainSession(), _FakeFarewell()
        wire_genesys_call_control(transport, session, farewell, telemetry, "genesys-conv-1")
        self.assertIsNotNone(farewell.end_call)
        # WHEN the customer confirms the end-of-call (ADR-0035 confirmation turn)
        await farewell.end_call("confirmation")
        await asyncio.sleep(0)  # let the off-task drain future run
        # THEN the reason is customer_farewell and the shared drain path is used (no bespoke close)
        ends = [e for e in telemetry.events() if e.name == CALL_END_EVENT]
        self.assertEqual([e.attributes["reason"] for e in ends], [REASON_CUSTOMER_FAREWELL])
        self.assertEqual(ends[0].attributes["signal"], "confirmation")
        self.assertEqual(session.drained, 1)

    async def test_peer_disconnect_records_reason_then_drains(self):
        # GIVEN a wired Genesys session
        telemetry = TelemetryRecorder()
        transport, session, farewell = _FakeTransport(), _FakeDrainSession(), _FakeFarewell()
        wire_genesys_call_control(transport, session, farewell, telemetry, "genesys-conv-1")
        # WHEN the peer disconnects (the AudioHook socket goes away)
        await transport.handlers["on_client_disconnected"](transport, object())
        # THEN the ending is recorded as client_disconnect and the session is drained once
        ends = [e for e in telemetry.events() if e.name == CALL_END_EVENT]
        self.assertEqual([e.attributes["reason"] for e in ends], [REASON_CLIENT_DISCONNECT])
        self.assertEqual(session.drained, 1)


if __name__ == "__main__":
    unittest.main()
