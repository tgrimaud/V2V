"""TASK-WEB-028: the interim browser WebSocket signaling is a thin transport adapter
over the shared session core — it builds the socle transport (WEB-026), assembles the
session through the shared `SessionFactory` (WEB-027), and runs it on the background loop.

These tests drive it through fakes (no real socket bind): a fake transport-builder returns
a fake transport that captures pipecat event-handler registrations, a fake factory returns
a fake session, and a fake loop records the spawned run coroutine. Live socket behaviour
(single-client 1013 refusal, real media) is covered by the WEB-026 socle tests + WEB-031 QA.
"""

import asyncio
import os
import unittest

from voice_common.telemetry import TelemetryRecorder
from web_voice.websocket_signaling import (
    ACTIVE_SESSIONS_METRIC,
    CLIENT_CONNECTED_EVENT,
    CLIENT_DISCONNECTED_EVENT,
    DEFAULT_MAX_WS_SESSIONS,
    DEFAULT_WS_PORT,
    REASON_SINGLE_CLIENT,
    SESSION_REJECTED_EVENT,
    SESSION_STARTED_EVENT,
    WebSocketSignalingService,
    ws_language_config,
    ws_max_sessions_config,
    ws_port_config,
)


class _FakeSession:
    def __init__(self) -> None:
        self.stopped = False

    async def run(self) -> None:  # spawned onto the loop (never actually awaited in tests)
        return None

    async def stop(self) -> None:
        self.stopped = True


class _FakeFactory:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session
        self.calls: list[tuple] = []

    def build_session(self, transport, envelope, telemetry):
        self.calls.append((transport, envelope, telemetry))
        return self._session, None


class _FakeTransport:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.built_with: dict = {}

    def event_handler(self, name: str):
        def register(fn):
            self.handlers[name] = fn
            return fn

        return register


class _FakeLoop:
    def __init__(self) -> None:
        self.spawned = 0

    def spawn(self, coro):
        # We are not running the pipeline in the unit test; close the coroutine so Python
        # does not warn about it never being awaited, and just record that spawn happened.
        coro.close()
        self.spawned += 1
        return object()

    def run(self, coro, *, timeout=None):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


class _FakeRequest:
    def __init__(self, path: str) -> None:
        self.path = path


class _FakeWebSocket:
    def __init__(self, path: str) -> None:
        self.request = _FakeRequest(path)


def _build_service(**overrides):
    transport = _FakeTransport()
    session = _FakeSession()
    factory = _FakeFactory(session)
    loop = _FakeLoop()
    captured = {}

    def transport_builder(
        host, port, *, sample_rate, serializer, allowed_origins, on_client_rejected=None
    ):
        captured["host"] = host
        captured["port"] = port
        captured["sample_rate"] = sample_rate
        captured["serializer"] = serializer
        captured["allowed_origins"] = allowed_origins
        captured["on_client_rejected"] = on_client_rejected
        return transport

    service = WebSocketSignalingService(
        factory=factory,
        loop=loop,
        transport_builder=transport_builder,
        **overrides,
    )
    return service, transport, session, factory, loop, captured


class WebSocketSignalingStartTest(unittest.TestCase):
    def test_start_builds_transport_and_spawns_the_session_on_the_loop(self) -> None:
        # GIVEN a WS signaling service wired to a fake factory/loop/transport
        service, transport, _session, factory, loop, captured = _build_service(
            host="0.0.0.0", port=9099, default_language="fr"
        )
        telemetry = TelemetryRecorder()
        service._telemetry_factory = lambda: telemetry
        # WHEN it is started
        correlation_id = service.start()
        # THEN the socle transport is built at the configured host/port with the framing serializer
        self.assertEqual(captured["host"], "0.0.0.0")
        self.assertEqual(captured["port"], 9099)
        self.assertEqual(captured["sample_rate"], service._sample_rate)
        self.assertIsNotNone(captured["serializer"])
        # AND the session is assembled via the shared factory and spawned on the loop
        self.assertEqual(len(factory.calls), 1)
        self.assertIs(factory.calls[0][0], transport)
        self.assertEqual(loop.spawned, 1)
        # AND a session-started event carries the correlation id + effective language
        started = [e for e in telemetry.events() if e.name == SESSION_STARTED_EVENT]
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0].attributes["correlation_id"], correlation_id)
        self.assertEqual(started[0].attributes["effective_language"], "fr")

    def test_default_language_none_reports_auto(self) -> None:
        # GIVEN no server default language
        service, _t, _s, _f, _l, _c = _build_service()
        telemetry = TelemetryRecorder()
        service._telemetry_factory = lambda: telemetry
        # WHEN started
        service.start()
        # THEN the effective language is reported as auto-detect (backend decides)
        started = [e for e in telemetry.events() if e.name == SESSION_STARTED_EVENT]
        self.assertEqual(started[0].attributes["effective_language"], "auto")


class WebSocketSignalingClientEventsTest(unittest.TestCase):
    def test_on_client_connected_records_the_declared_language_from_the_ws_query(self) -> None:
        # GIVEN a started service and a client whose WS URL declares ?language=en
        service, transport, _s, _f, _l, _c = _build_service(default_language="fr")
        telemetry = TelemetryRecorder()
        service._telemetry_factory = lambda: telemetry
        service.start()
        websocket = _FakeWebSocket("/?language=en")
        # WHEN the transport fires its on_client_connected callback
        asyncio.run(transport.handlers["on_client_connected"](transport, websocket))
        # THEN the declared language is captured, effective language stays the server default
        connected = [e for e in telemetry.events() if e.name == CLIENT_CONNECTED_EVENT]
        self.assertEqual(len(connected), 1)
        self.assertEqual(connected[0].attributes["declared_language"], "en")
        self.assertEqual(connected[0].attributes["effective_language"], "fr")

    def test_on_client_disconnected_is_recorded(self) -> None:
        service, transport, _s, _f, _l, _c = _build_service()
        telemetry = TelemetryRecorder()
        service._telemetry_factory = lambda: telemetry
        service.start()
        asyncio.run(transport.handlers["on_client_disconnected"](transport, _FakeWebSocket("/")))
        disconnected = [e for e in telemetry.events() if e.name == CLIENT_DISCONNECTED_EVENT]
        self.assertEqual(len(disconnected), 1)

    def test_declared_language_absent_is_none(self) -> None:
        service, _t, _s, _f, _l, _c = _build_service()
        self.assertIsNone(service._declared_language(_FakeWebSocket("/")))
        self.assertIsNone(service._declared_language(_FakeWebSocket("")))


class WebSocketSignalingCapacityTest(unittest.TestCase):
    """TASK-WEB-030 AC#1: session ceiling is observable — active-session gauge on
    connect/disconnect and a clean refusal (gauge + event) for an extra concurrent client."""

    def test_connect_then_disconnect_emit_the_active_session_gauge(self) -> None:
        # GIVEN a started service
        service, transport, _s, _f, _l, _c = _build_service()
        telemetry = TelemetryRecorder()
        service._telemetry_factory = lambda: telemetry
        service.start()
        # WHEN a client connects then disconnects
        asyncio.run(transport.handlers["on_client_connected"](transport, _FakeWebSocket("/")))
        asyncio.run(transport.handlers["on_client_disconnected"](transport, _FakeWebSocket("/")))
        # THEN the active-session gauge is emitted with 1 (accepted) then 0 (closed)
        gauges = [m for m in telemetry.metrics() if m.name == ACTIVE_SESSIONS_METRIC]
        self.assertEqual([(g.value, g.attributes["outcome"]) for g in gauges], [(1.0, "accepted"), (0.0, "closed")])
        self.assertTrue(all(g.attributes["max_sessions"] == 1 for g in gauges))

    def test_extra_concurrent_client_is_refused_with_gauge_and_event(self) -> None:
        # GIVEN a started service that already has one connected client
        service, transport, _s, _f, _l, _c = _build_service()
        telemetry = TelemetryRecorder()
        service._telemetry_factory = lambda: telemetry
        service.start()
        asyncio.run(transport.handlers["on_client_connected"](transport, _FakeWebSocket("/")))
        # WHEN the socle refuses an extra concurrent client (WS 1013) via the callback
        asyncio.run(service._on_client_rejected(_FakeWebSocket("/")))
        # THEN a refusal event carries the single-client reason + capacity, and the gauge
        # records the rejection (no crash)
        rejected = [e for e in telemetry.events() if e.name == SESSION_REJECTED_EVENT]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].attributes["reason"], REASON_SINGLE_CLIENT)
        self.assertEqual(rejected[0].attributes["active_sessions"], 1)
        self.assertEqual(rejected[0].attributes["max_sessions"], 1)
        self.assertTrue(any(m.attributes["outcome"] == "rejected" for m in telemetry.metrics() if m.name == ACTIVE_SESSIONS_METRIC))

    def test_start_passes_the_rejection_callback_to_the_transport_builder(self) -> None:
        # GIVEN a started service
        service, _t, _s, _f, _l, captured = _build_service()
        service._telemetry_factory = lambda: TelemetryRecorder()
        service.start()
        # THEN the transport is built with the signaling rejection callback wired in
        # (bound methods compare equal by (instance, func), but are not identity-stable)
        self.assertEqual(captured["on_client_rejected"], service._on_client_rejected)


class WebSocketSignalingTeardownTest(unittest.TestCase):
    def test_close_stops_the_session_and_dumps_telemetry_once(self) -> None:
        # GIVEN a started service with a fake log sink
        logged: list[TelemetryRecorder] = []
        service, _t, session, _f, _l, _c = _build_service(log=logged.append)
        telemetry = TelemetryRecorder()
        service._telemetry_factory = lambda: telemetry
        service.start()
        # WHEN closed
        service.close()
        # THEN the session is stopped and the call telemetry is dumped exactly once
        self.assertTrue(session.stopped)
        self.assertEqual(logged, [telemetry])

    def test_disconnect_dumps_call_evidence_and_close_does_not_double_dump(self) -> None:
        # GIVEN a started service with a fake log sink (TASK-WEB-030: per-call dump at call end)
        logged: list[TelemetryRecorder] = []
        service, transport, session, _f, _l, _c = _build_service(log=logged.append)
        telemetry = TelemetryRecorder()
        service._telemetry_factory = lambda: telemetry
        service.start()
        # WHEN the client disconnects (call ends) and the server is later shut down
        asyncio.run(transport.handlers["on_client_disconnected"](transport, _FakeWebSocket("/")))
        service.close()
        # THEN the call evidence is dumped exactly once (disconnect), not again on close
        self.assertEqual(logged, [telemetry])


class WebSocketConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            k: os.environ.get(k)
            for k in ("VOICE_WS_PORT", "VOICE_WS_LANGUAGE", "VOICE_MAX_WS_SESSIONS")
        }

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_port_defaults_and_rejects_garbage(self) -> None:
        os.environ.pop("VOICE_WS_PORT", None)
        self.assertEqual(ws_port_config(), DEFAULT_WS_PORT)
        os.environ["VOICE_WS_PORT"] = "not-a-port"
        self.assertEqual(ws_port_config(), DEFAULT_WS_PORT)
        os.environ["VOICE_WS_PORT"] = "0"
        self.assertEqual(ws_port_config(), DEFAULT_WS_PORT)
        os.environ["VOICE_WS_PORT"] = "8092"
        self.assertEqual(ws_port_config(), 8092)

    def test_language_config_normalises_and_defaults_to_none(self) -> None:
        os.environ.pop("VOICE_WS_LANGUAGE", None)
        self.assertIsNone(ws_language_config())
        os.environ["VOICE_WS_LANGUAGE"] = "  FR "
        self.assertEqual(ws_language_config(), "fr")

    def test_max_sessions_defaults_and_rejects_non_positive_or_garbage(self) -> None:
        os.environ.pop("VOICE_MAX_WS_SESSIONS", None)
        self.assertEqual(ws_max_sessions_config(), DEFAULT_MAX_WS_SESSIONS)
        os.environ["VOICE_MAX_WS_SESSIONS"] = "not-a-number"
        self.assertEqual(ws_max_sessions_config(), DEFAULT_MAX_WS_SESSIONS)
        os.environ["VOICE_MAX_WS_SESSIONS"] = "0"
        self.assertEqual(ws_max_sessions_config(), DEFAULT_MAX_WS_SESSIONS)
        os.environ["VOICE_MAX_WS_SESSIONS"] = "3"
        self.assertEqual(ws_max_sessions_config(), 3)


if __name__ == "__main__":
    unittest.main()
