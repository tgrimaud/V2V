"""TASK-WEB-038 slice 2 (ADR-0047): the aiohttp-native WebSocket voice transport +
single-port `GET /ws` handler.

Two layers:
- **Transport** (`AiohttpWebsocketTransport`): driven by a REAL aiohttp WS connection
  (`TestServer`/`TestClient`) through a REAL pipecat pipeline, proving binary PCM in
  becomes `InputAudioRawFrame`s and an outgoing control frame reaches the client — i.e.
  the aiohttp socket bridges pipecat exactly like the FastAPI transport, with no FastAPI.
- **Handler** (`make_ws_handler`): the per-connection lifecycle, the concurrency ceiling
  (extra client refused with WS 1013), and the telemetry parity (session started /
  client connected / disconnected + active-session gauge), driven with a fake factory +
  controllable fake session so no provider/backend is needed.

Live media round-trip (real STT/TTS bytes over the socket) is covered by the QA behave
suite + the slice live-boot smoke, not re-simulated here.
"""

import array
import asyncio
import os
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from aiohttp import WSMsgType, web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
    Frame,
    InputAudioRawFrame,
    OutputTransportMessageUrgentFrame,
    StartFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineTask  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402

from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice.websocket_app import (  # noqa: E402
    ACTIVE_SESSIONS_METRIC,
    CLIENT_CONNECTED_EVENT,
    CLIENT_DISCONNECTED_EVENT,
    DEFAULT_MAX_WS_SESSIONS_ASYNC,
    REASON_CAPACITY,
    SESSION_REJECTED_EVENT,
    SESSION_STARTED_EVENT,
    WS_TRY_AGAIN_LATER,
    AiohttpWebsocketTransport,
    build_aiohttp_ws_transport,
    make_ws_handler,
    ws_async_max_sessions_config,
    _wire_disconnect_drain,
)


def _pcm(ms: float, peak: int, *, sample_rate: int = 16000) -> bytes:
    return array.array("h", [peak] * int(sample_rate * ms / 1000)).tobytes()


async def _wait_for(predicate, *, timeout: float = 10.0) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(0.02)


# --------------------------------------------------------------------------- #
# Transport layer: real aiohttp WS + real pipecat pipeline                    #
# --------------------------------------------------------------------------- #


class _CaptureInput(FrameProcessor):
    """Downstream sink recording the audio the transport pushes into the pipeline."""

    def __init__(self) -> None:
        super().__init__()
        self.audio = bytearray()
        self.got = asyncio.Event()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            self.audio.extend(frame.audio)
            self.got.set()
        await self.push_frame(frame, direction)


class _EmitOnStart(FrameProcessor):
    """Pushes one output control frame downstream once the pipeline starts."""

    def __init__(self, frame: Frame) -> None:
        super().__init__()
        self._frame = frame

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            await self.push_frame(self._frame, FrameDirection.DOWNSTREAM)


class _EmitAudioOnStart(FrameProcessor):
    """Pushes one TTS audio frame downstream once the pipeline starts."""

    def __init__(self, audio: bytes, *, sample_rate: int = 16000) -> None:
        super().__init__()
        self._audio = audio
        self._sample_rate = sample_rate

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            await self.push_frame(
                TTSAudioRawFrame(
                    audio=self._audio, sample_rate=self._sample_rate, num_channels=1
                ),
                FrameDirection.DOWNSTREAM,
            )


def _pipeline_task(pipeline: Pipeline) -> PipelineTask:
    return PipelineTask(
        pipeline,
        params=PipelineParams(),
        enable_rtvi=False,
        enable_turn_tracking=False,
        cancel_on_idle_timeout=False,
        check_dangling_tasks=False,
    )


class AiohttpWebsocketTransportTest(unittest.IsolatedAsyncioTestCase):
    async def _serve(self, build_pipeline) -> TestClient:
        async def handler(request: web.Request) -> web.WebSocketResponse:
            websocket = web.WebSocketResponse()
            await websocket.prepare(request)
            transport = build_aiohttp_ws_transport(websocket)
            pipeline, captured = build_pipeline(transport)
            request.app["captured"] = captured
            task = _pipeline_task(pipeline)
            request.app["task"] = task
            await PipelineRunner(handle_sigint=False).run(task)
            return websocket

        app = web.Application()
        app.router.add_get("/ws", handler)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_binary_message_becomes_an_input_audio_frame(self) -> None:
        # GIVEN a transport wired to a capture sink over a real aiohttp WS
        def build(transport: AiohttpWebsocketTransport):
            capture = _CaptureInput()
            return Pipeline([transport.input(), capture]), capture

        client = await self._serve(build)
        websocket = await client.ws_connect("/ws")
        # WHEN the client sends a binary PCM16 frame
        payload = _pcm(30, 2000)
        await websocket.send_bytes(payload)
        # THEN the transport deserializes it and pushes it into the pipeline as audio
        capture = client.app["captured"]
        await _wait_for(capture.got.is_set)
        self.assertEqual(bytes(capture.audio), payload)
        await websocket.close()

    async def test_tts_audio_frame_reaches_the_client_as_binary_pcm(self) -> None:
        # GIVEN a pipeline that emits a TTS audio frame toward the transport output
        peak = 2000
        payload = _pcm(500, peak)  # 500ms overshoots any single audio chunk size

        def build(transport: AiohttpWebsocketTransport):
            emit = _EmitAudioOnStart(payload)
            return Pipeline([transport.input(), emit, transport.output()]), None

        client = await self._serve(build)
        websocket = await client.ws_connect("/ws")
        # WHEN the output serializes the audio and writes it to the socket
        received = bytearray()
        try:
            while len(received) < len(payload):
                message = await asyncio.wait_for(websocket.receive(), timeout=3)
                if message.type == WSMsgType.BINARY:
                    received.extend(message.data)
                elif message.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                    break
        except asyncio.TimeoutError:
            pass
        # THEN the client receives real PCM16 bytes (write_audio_frame -> serialize -> send_bytes)
        self.assertGreater(len(received), 0)
        self.assertEqual(len(received) % 2, 0)
        self.assertEqual(set(array.array("h", bytes(received))), {peak})
        await websocket.close()

    async def test_output_control_frame_reaches_the_client_as_json_text(self) -> None:
        # GIVEN a pipeline that emits an OPENED control frame toward the transport output
        def build(transport: AiohttpWebsocketTransport):
            emit = _EmitOnStart(OutputTransportMessageUrgentFrame(message={"type": "opened"}))
            return Pipeline([transport.input(), emit, transport.output()]), None

        client = await self._serve(build)
        websocket = await client.ws_connect("/ws")
        # WHEN the pipeline starts and the output serializes the control frame
        message = await asyncio.wait_for(websocket.receive(), timeout=10)
        # THEN the client receives it as a JSON text frame (control channel)
        self.assertEqual(message.type, WSMsgType.TEXT)
        self.assertIn("opened", message.data)
        await websocket.close()


# --------------------------------------------------------------------------- #
# Handler layer: lifecycle, capacity ceiling, telemetry parity                #
# --------------------------------------------------------------------------- #


class _FakeSession:
    """A session whose `run()` blocks until released, recording drain/stop calls."""

    def __init__(self) -> None:
        self.ran = False
        self.drained = False
        self.stopped = False
        self._release = asyncio.Event()

    async def run(self) -> None:
        self.ran = True
        await self._release.wait()

    async def drain(self) -> None:
        self.drained = True
        self._release.set()

    async def stop(self) -> None:
        self.stopped = True
        self._release.set()

    def release(self) -> None:
        self._release.set()


class _FakeFactory:
    def __init__(self) -> None:
        self.sessions: list[_FakeSession] = []
        self.transports: list[object] = []

    def build_session(self, transport, envelope, telemetry):
        session = _FakeSession()
        self.sessions.append(session)
        self.transports.append(transport)
        return session, None


class WsHandlerLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def _serve(self, handler) -> TestClient:
        app = web.Application()
        app.router.add_get("/ws", handler)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_accepted_connection_records_started_connected_and_accepted_gauge(self) -> None:
        # GIVEN a handler with a shared telemetry recorder and a blocking fake session
        shared = TelemetryRecorder()
        logged: list[TelemetryRecorder] = []
        factory = _FakeFactory()
        handler = make_ws_handler(
            factory,
            default_language="fr",
            max_sessions=2,
            telemetry_factory=lambda: shared,
            log=logged.append,
        )
        client = await self._serve(handler)
        # WHEN a client connects declaring ?language=en
        websocket = await client.ws_connect("/ws?language=en")
        await _wait_for(lambda: bool(factory.sessions) and factory.sessions[0].ran)
        # THEN session-started + client-connected + an accepted active-session gauge are recorded
        names = [e.name for e in shared.events()]
        self.assertIn(SESSION_STARTED_EVENT, names)
        connected = [e for e in shared.events() if e.name == CLIENT_CONNECTED_EVENT]
        self.assertEqual(connected[0].attributes["declared_language"], "en")
        self.assertEqual(connected[0].attributes["effective_language"], "fr")
        accepted = [
            m
            for m in shared.metrics()
            if m.name == ACTIVE_SESSIONS_METRIC and m.attributes["outcome"] == "accepted"
        ]
        self.assertEqual(accepted[0].value, 1.0)
        # AND on teardown the session is stopped, the closed gauge fires, telemetry dumps once
        factory.sessions[0].release()
        await _wait_for(lambda: bool(logged))
        self.assertTrue(factory.sessions[0].stopped)
        self.assertIn(CLIENT_DISCONNECTED_EVENT, [e.name for e in shared.events()])
        closed = [
            m
            for m in shared.metrics()
            if m.name == ACTIVE_SESSIONS_METRIC and m.attributes["outcome"] == "closed"
        ]
        self.assertEqual(closed[0].value, 0.0)
        self.assertEqual(logged, [shared])
        await websocket.close()

    async def test_over_capacity_connection_is_refused_with_ws_1013(self) -> None:
        # GIVEN a handler capped at one concurrent session
        logged: list[TelemetryRecorder] = []
        factory = _FakeFactory()
        handler = make_ws_handler(factory, max_sessions=1, log=logged.append)
        client = await self._serve(handler)
        first = await client.ws_connect("/ws")
        await _wait_for(lambda: bool(factory.sessions) and factory.sessions[0].ran)
        # WHEN a second concurrent client connects
        second = await client.ws_connect("/ws")
        message = await asyncio.wait_for(second.receive(), timeout=10)
        # THEN the server closes it with WS 1013 (try again later)
        self.assertIn(message.type, (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED))
        self.assertEqual(second.close_code, WS_TRY_AGAIN_LATER)
        # AND only one session was ever built (the extra client never reached the factory)
        self.assertEqual(len(factory.sessions), 1)
        # AND a refusal event + rejected gauge were recorded on the reject telemetry
        rejected_recorders = [
            rec for rec in logged if any(e.name == SESSION_REJECTED_EVENT for e in rec.events())
        ]
        self.assertEqual(len(rejected_recorders), 1)
        event = next(e for e in rejected_recorders[0].events() if e.name == SESSION_REJECTED_EVENT)
        self.assertEqual(event.attributes["reason"], REASON_CAPACITY)
        self.assertEqual(event.attributes["max_sessions"], 1)
        self.assertTrue(
            any(
                m.attributes["outcome"] == "rejected"
                for m in rejected_recorders[0].metrics()
                if m.name == ACTIVE_SESSIONS_METRIC
            )
        )
        factory.sessions[0].release()
        await first.close()
        await second.close()

    async def test_disconnect_drains_the_session_so_run_returns(self) -> None:
        # GIVEN a real transport wired to a fake session via the handler's drain wiring
        session = _FakeSession()

        class _DummyWS:
            closed = False

        transport = build_aiohttp_ws_transport(_DummyWS())
        _wire_disconnect_drain(transport, session)
        # WHEN the transport fires on_client_disconnected (peer went away). The event
        # dispatches the handler as a task (BaseObject default), so yield until it runs.
        await transport._call_event_handler("on_client_disconnected", object())
        await _wait_for(lambda: session.drained)
        # THEN the session was drained (queues an EndFrame so run() returns on its own)
        self.assertTrue(session.drained)


class WsMaxSessionsConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.get("VOICE_MAX_WS_SESSIONS")

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop("VOICE_MAX_WS_SESSIONS", None)
        else:
            os.environ["VOICE_MAX_WS_SESSIONS"] = self._saved

    def test_defaults_and_rejects_non_positive_or_garbage(self) -> None:
        os.environ.pop("VOICE_MAX_WS_SESSIONS", None)
        self.assertEqual(ws_async_max_sessions_config(), DEFAULT_MAX_WS_SESSIONS_ASYNC)
        os.environ["VOICE_MAX_WS_SESSIONS"] = "not-a-number"
        self.assertEqual(ws_async_max_sessions_config(), DEFAULT_MAX_WS_SESSIONS_ASYNC)
        os.environ["VOICE_MAX_WS_SESSIONS"] = "0"
        self.assertEqual(ws_async_max_sessions_config(), DEFAULT_MAX_WS_SESSIONS_ASYNC)
        os.environ["VOICE_MAX_WS_SESSIONS"] = "5"
        self.assertEqual(ws_async_max_sessions_config(), 5)


class BuildWsHandlerBranchTest(unittest.TestCase):
    """server.py `_build_ws_handler`: `--websocket off` disables `/ws`; auto/on enable it."""

    @staticmethod
    def _args(websocket: str):
        from types import SimpleNamespace

        return SimpleNamespace(
            websocket=websocket, stt_mode="batch", tts_mode="batch", provider="fixture"
        )

    def test_websocket_off_yields_no_handler(self) -> None:
        from web_voice.server import _build_ws_handler

        handler = _build_ws_handler(self._args("off"), object(), object(), object())
        self.assertIsNone(handler)

    def test_websocket_auto_and_on_yield_a_callable_handler(self) -> None:
        from web_voice.server import _build_ws_handler

        for mode in ("auto", "on"):
            with self.subTest(mode=mode):
                handler = _build_ws_handler(self._args(mode), object(), object(), object())
                self.assertTrue(callable(handler))


if __name__ == "__main__":
    unittest.main()
