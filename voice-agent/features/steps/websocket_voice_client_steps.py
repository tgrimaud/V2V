"""Behave steps for the interim browser WebSocket voice client wiring (TASK-WEB-028).

Driven through fakes (no real socket bind): the transport-builder returns a fake transport
that captures pipecat event-handler registrations, the factory returns a fake session, and
the loop records the spawned run. Live media + the 1013 refusal are covered by the socle
tests (WEB-026) and WEB-031 QA.
"""

import asyncio

from behave import given, then, when

from voice_common.telemetry import TelemetryRecorder
from web_voice.websocket_signaling import (
    CLIENT_CONNECTED_EVENT,
    SESSION_STARTED_EVENT,
    WebSocketSignalingService,
)
from web_voice.websocket_support import build_websocket_audio_transport


class _FakeSession:
    def __init__(self):
        self.stopped = False

    async def run(self):
        return None

    async def stop(self):
        self.stopped = True


class _FakeFactory:
    def __init__(self, session):
        self._session = session
        self.calls = []

    def build_session(self, transport, envelope, telemetry):
        self.calls.append((transport, envelope, telemetry))
        return self._session, None


class _FakeTransport:
    def __init__(self):
        self.handlers = {}

    def event_handler(self, name):
        def register(fn):
            self.handlers[name] = fn
            return fn

        return register


class _FakeLoop:
    def __init__(self):
        self.spawned = 0

    def spawn(self, coro):
        coro.close()
        self.spawned += 1
        return object()

    def run(self, coro, *, timeout=None):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


class _FakeWebSocket:
    def __init__(self, path):
        self.request = type("_Req", (), {"path": path})()


@given("the interim WebSocket voice signaling with a French server default")
def step_build_ws_signaling(context):
    context.ws_transport = _FakeTransport()
    context.ws_session = _FakeSession()
    context.ws_factory = _FakeFactory(context.ws_session)
    context.ws_loop = _FakeLoop()
    context.ws_telemetry = TelemetryRecorder()
    context.ws_service = WebSocketSignalingService(
        factory=context.ws_factory,
        loop=context.ws_loop,
        default_language="fr",
        telemetry_factory=lambda: context.ws_telemetry,
        transport_builder=lambda host, port, *, sample_rate, serializer, allowed_origins: context.ws_transport,
    )


@when("the WebSocket voice path starts")
@given("the WebSocket voice path has started")
def step_start_ws(context):
    context.ws_correlation_id = context.ws_service.start()


@then("it assembles a session through the shared session factory")
def step_factory_called(context):
    assert len(context.ws_factory.calls) == 1
    assert context.ws_factory.calls[0][0] is context.ws_transport


@then("it runs that session on the background loop")
def step_spawned(context):
    assert context.ws_loop.spawned == 1


@then('it records the call with the effective language "{language}"')
def step_records_effective_language(context, language):
    started = [e for e in context.ws_telemetry.events() if e.name == SESSION_STARTED_EVENT]
    assert len(started) == 1, started
    assert started[0].attributes["effective_language"] == language


@when('a browser client connects declaring the language "{language}"')
def step_client_connects(context, language):
    websocket = _FakeWebSocket(f"/?language={language}")
    asyncio.run(context.ws_transport.handlers["on_client_connected"](context.ws_transport, websocket))


@then('the declared language "{language}" is captured for correlation')
def step_declared_language(context, language):
    connected = [e for e in context.ws_telemetry.events() if e.name == CLIENT_CONNECTED_EVENT]
    assert len(connected) == 1, connected
    assert connected[0].attributes["declared_language"] == language


@then('the effective conversation language stays "{language}"')
def step_effective_stays(context, language):
    connected = [e for e in context.ws_telemetry.events() if e.name == CLIENT_CONNECTED_EVENT]
    assert connected[0].attributes["effective_language"] == language


@given("the voice bridge builds the WebSocket audio transport for the client path")
def step_build_socle(context):
    context.socle_transport = build_websocket_audio_transport("127.0.0.1", 8091)


@then("the transport is the single-client server variant that refuses a second client")
def step_single_client(context):
    assert context.socle_transport.__class__.__name__ == "SingleClientWebsocketServerTransport"
