"""TASK-WEB-041 / ADR-0049: the Genesys Audio Connector transport adapter handler.

The Genesys counterpart of `make_ws_handler` on the same ADR-0047 single async server.
Driven with a fake factory + a controllable fake session (no provider/backend needed),
this covers the transport boundary the ticket owns: the per-connection lifecycle +
telemetry (started / connected / disconnected + active-session gauge, all labelled
`genesys_audio_connector`), the deterministic `conversationId -> traceparent` stitch
(one trace), the concurrency ceiling (extra call refused with WS 1013), and the graceful
15-minute cap (at the cap the session is DRAINED, never silently cut).
"""

import asyncio
import os
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from aiohttp import WSMsgType, web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from voice_common.trace_context import derive_traceparent  # noqa: E402
from web_voice.envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL  # noqa: E402
from web_voice.genesys_app import (  # noqa: E402
    ACTIVE_SESSIONS_METRIC,
    CLIENT_CONNECTED_EVENT,
    CLIENT_DISCONNECTED_EVENT,
    DEFAULT_MAX_GENESYS_SESSIONS,
    DEFAULT_MAX_SESSION_S,
    REASON_CAP_REACHED,
    REASON_CAPACITY,
    SESSION_CAP_EVENT,
    SESSION_REJECTED_EVENT,
    SESSION_STARTED_EVENT,
    WS_TRY_AGAIN_LATER,
    _cancel_cap,
    _schedule_cap,
    genesys_codec_config,
    genesys_max_session_s_config,
    genesys_max_sessions_config,
    make_genesys_handler,
)


async def _wait_for(predicate, *, timeout: float = 10.0) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(0.02)


class _FakeSession:
    """A session whose `run()` blocks until `drain()`/`stop()` releases it."""

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
        self.envelopes: list[object] = []

    def build_session(self, transport, envelope, telemetry):
        session = _FakeSession()
        self.sessions.append(session)
        self.envelopes.append(envelope)
        return session, None


def _names(recorder: TelemetryRecorder) -> list[str]:
    return [event.name for event in recorder.events()]


def _gauge(recorder: TelemetryRecorder, outcome: str):
    return [
        metric
        for metric in recorder.metrics()
        if metric.name == ACTIVE_SESSIONS_METRIC and metric.attributes["outcome"] == outcome
    ]


class GenesysHandlerServeMixin(unittest.IsolatedAsyncioTestCase):
    async def _serve(self, handler) -> TestClient:
        app = web.Application()
        app.router.add_get("/genesys/audiohook", handler)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client


class GenesysHandlerLifecycleTest(GenesysHandlerServeMixin):
    async def test_accepted_call_records_started_connected_and_accepted_gauge(self) -> None:
        # GIVEN a handler with a shared recorder and a blocking fake session
        shared = TelemetryRecorder()
        logged: list[TelemetryRecorder] = []
        factory = _FakeFactory()
        handler = make_genesys_handler(
            factory, max_sessions=2, telemetry_factory=lambda: shared, log=logged.append
        )
        client = await self._serve(handler)
        # WHEN a Genesys call opens carrying its conversationId
        websocket = await client.ws_connect("/genesys/audiohook?conversationId=conv-9")
        await _wait_for(lambda: bool(factory.sessions) and factory.sessions[0].ran)
        # THEN started + connected fire and the accepted gauge reads 1, all Genesys-labelled
        self.assertIn(SESSION_STARTED_EVENT, _names(shared))
        connected = next(e for e in shared.events() if e.name == CLIENT_CONNECTED_EVENT)
        self.assertEqual(connected.attributes["channel"], GENESYS_AUDIO_CONNECTOR_CHANNEL)
        self.assertEqual(_gauge(shared, "accepted")[0].value, 1.0)
        # AND on teardown the session is stopped, the closed gauge fires and telemetry dumps once
        factory.sessions[0].release()
        await _wait_for(lambda: bool(logged))
        self.assertTrue(factory.sessions[0].stopped)
        self.assertIn(CLIENT_DISCONNECTED_EVENT, _names(shared))
        self.assertEqual(_gauge(shared, "closed")[0].value, 0.0)
        self.assertEqual(logged, [shared])
        await websocket.close()

    async def test_conversation_id_becomes_the_deterministic_one_trace_traceparent(self) -> None:
        # GIVEN a handler and a call whose Genesys conversationId is known
        shared = TelemetryRecorder()
        factory = _FakeFactory()
        handler = make_genesys_handler(
            factory, telemetry_factory=lambda: shared, log=lambda _r: None
        )
        client = await self._serve(handler)
        # WHEN the call opens with ?conversationId=conv-trace
        websocket = await client.ws_connect("/genesys/audiohook?conversationId=conv-trace")
        await _wait_for(lambda: bool(factory.sessions) and factory.sessions[0].ran)
        # THEN the started event carries the traceparent DERIVED from that id (one trace),
        # and the envelope correlation id is the conversationId (Genesys leg + backend stitch)
        started = next(e for e in shared.events() if e.name == SESSION_STARTED_EVENT)
        self.assertEqual(started.attributes["traceparent"], derive_traceparent("conv-trace"))
        self.assertEqual(factory.envelopes[0].correlation_id, "conv-trace")
        factory.sessions[0].release()
        await websocket.close()

    async def test_over_capacity_call_is_refused_with_ws_1013(self) -> None:
        # GIVEN a handler capped at one concurrent Genesys session
        logged: list[TelemetryRecorder] = []
        factory = _FakeFactory()
        handler = make_genesys_handler(factory, max_sessions=1, log=logged.append)
        client = await self._serve(handler)
        first = await client.ws_connect("/genesys/audiohook?conversationId=a")
        await _wait_for(lambda: bool(factory.sessions) and factory.sessions[0].ran)
        # WHEN a second concurrent call arrives
        second = await client.ws_connect("/genesys/audiohook?conversationId=b")
        message = await asyncio.wait_for(second.receive(), timeout=10)
        # THEN it is closed with WS 1013 (try again later) and never reaches the factory
        self.assertIn(message.type, (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED))
        self.assertEqual(second.close_code, WS_TRY_AGAIN_LATER)
        self.assertEqual(len(factory.sessions), 1)
        # AND a capacity refusal + rejected gauge were recorded (Genesys-labelled)
        rejected = [r for r in logged if any(e.name == SESSION_REJECTED_EVENT for e in r.events())]
        self.assertEqual(len(rejected), 1)
        event = next(e for e in rejected[0].events() if e.name == SESSION_REJECTED_EVENT)
        self.assertEqual(event.attributes["reason"], REASON_CAPACITY)
        self.assertEqual(event.attributes["channel"], GENESYS_AUDIO_CONNECTOR_CHANNEL)
        self.assertTrue(_gauge(rejected[0], "rejected"))
        factory.sessions[0].release()
        await first.close()
        await second.close()


class GenesysCapTest(GenesysHandlerServeMixin):
    async def test_reaching_the_cap_drains_the_session_gracefully(self) -> None:
        # GIVEN a handler with a very short call cap and a shared recorder
        shared = TelemetryRecorder()
        logged: list[TelemetryRecorder] = []
        factory = _FakeFactory()
        handler = make_genesys_handler(
            factory, max_sessions=2, max_session_s=0.05,
            telemetry_factory=lambda: shared, log=logged.append,
        )
        client = await self._serve(handler)
        # WHEN a call opens and stays silent past the cap
        websocket = await client.ws_connect("/genesys/audiohook?conversationId=capped")
        await _wait_for(lambda: bool(logged))
        # THEN the cap fired, the session was DRAINED (not silently cut) and the call closed
        cap = next(e for e in shared.events() if e.name == SESSION_CAP_EVENT)
        self.assertEqual(cap.attributes["reason"], REASON_CAP_REACHED)
        self.assertEqual(cap.attributes["channel"], GENESYS_AUDIO_CONNECTOR_CHANNEL)
        self.assertTrue(factory.sessions[0].drained)
        self.assertIn(CLIENT_DISCONNECTED_EVENT, _names(shared))
        await websocket.close()

    async def test_a_call_ending_before_the_cap_records_no_cap_event(self) -> None:
        # GIVEN a generous cap and a call that ends promptly on its own
        shared = TelemetryRecorder()
        logged: list[TelemetryRecorder] = []
        factory = _FakeFactory()
        handler = make_genesys_handler(
            factory, max_sessions=2, max_session_s=100.0,
            telemetry_factory=lambda: shared, log=logged.append,
        )
        client = await self._serve(handler)
        websocket = await client.ws_connect("/genesys/audiohook?conversationId=quick")
        await _wait_for(lambda: bool(factory.sessions) and factory.sessions[0].ran)
        # WHEN the session finishes well before the cap
        factory.sessions[0].release()
        await _wait_for(lambda: bool(logged))
        # THEN no cap event is recorded (the cap timer was cancelled on teardown)
        self.assertNotIn(SESSION_CAP_EVENT, _names(shared))
        await websocket.close()


class GenesysCapSchedulingUnitTest(unittest.TestCase):
    def test_scheduling_is_disabled_when_cap_is_non_positive(self) -> None:
        # GIVEN a disabled cap (max_session_s <= 0) THEN no timer task is armed
        self.assertIsNone(_schedule_cap(object(), TelemetryRecorder(), "cid", 0))
        self.assertIsNone(_schedule_cap(object(), TelemetryRecorder(), "cid", -1))

    def test_cancelling_a_missing_cap_is_a_no_op(self) -> None:
        _cancel_cap(None)  # must not raise


class GenesysConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "VOICE_GENESYS_MAX_SESSIONS",
                "VOICE_GENESYS_MAX_SESSION_S",
                "VOICE_GENESYS_CODEC",
            )
        }

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_max_sessions_defaults_and_rejects_garbage_or_non_positive(self) -> None:
        os.environ.pop("VOICE_GENESYS_MAX_SESSIONS", None)
        self.assertEqual(genesys_max_sessions_config(), DEFAULT_MAX_GENESYS_SESSIONS)
        for bad in ("not-a-number", "0", "-2"):
            os.environ["VOICE_GENESYS_MAX_SESSIONS"] = bad
            self.assertEqual(genesys_max_sessions_config(), DEFAULT_MAX_GENESYS_SESSIONS)
        os.environ["VOICE_GENESYS_MAX_SESSIONS"] = "5"
        self.assertEqual(genesys_max_sessions_config(), 5)

    def test_max_session_s_defaults_and_allows_disabling(self) -> None:
        os.environ.pop("VOICE_GENESYS_MAX_SESSION_S", None)
        self.assertEqual(genesys_max_session_s_config(), DEFAULT_MAX_SESSION_S)
        os.environ["VOICE_GENESYS_MAX_SESSION_S"] = "garbage"
        self.assertEqual(genesys_max_session_s_config(), DEFAULT_MAX_SESSION_S)
        os.environ["VOICE_GENESYS_MAX_SESSION_S"] = "0"  # explicit disable is honoured
        self.assertEqual(genesys_max_session_s_config(), 0.0)

    def test_codec_defaults_to_l16_and_falls_back_on_unknown(self) -> None:
        os.environ.pop("VOICE_GENESYS_CODEC", None)
        self.assertEqual(genesys_codec_config(), "L16")
        os.environ["VOICE_GENESYS_CODEC"] = "pcmu"  # case-insensitive
        self.assertEqual(genesys_codec_config(), "PCMU")
        os.environ["VOICE_GENESYS_CODEC"] = "opus"  # unsupported -> default
        self.assertEqual(genesys_codec_config(), "L16")


class BuildGenesysHandlerBranchTest(unittest.TestCase):
    """server.py `_build_genesys_handler`: `--genesys off` disables it; auto/on enable it."""

    @staticmethod
    def _args(genesys: str):
        from types import SimpleNamespace

        return SimpleNamespace(
            genesys=genesys, stt_mode="batch", tts_mode="batch", provider="fixture"
        )

    def test_genesys_off_yields_no_handler(self) -> None:
        from web_voice.server import _build_genesys_handler

        handler = _build_genesys_handler(self._args("off"), object(), object(), object())
        self.assertIsNone(handler)

    def test_genesys_auto_and_on_yield_a_callable_handler(self) -> None:
        from web_voice.server import _build_genesys_handler

        for mode in ("auto", "on"):
            with self.subTest(mode=mode):
                handler = _build_genesys_handler(self._args(mode), object(), object(), object())
                self.assertTrue(callable(handler))


if __name__ == "__main__":
    unittest.main()
