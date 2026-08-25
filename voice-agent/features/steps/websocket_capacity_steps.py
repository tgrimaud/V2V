import asyncio

from behave import given, then, when

from voice_common.telemetry import TelemetryRecorder
from web_voice.session_telemetry import build_payload
from web_voice.websocket_signaling import (
    ACTIVE_SESSIONS_METRIC,
    REASON_SINGLE_CLIENT,
    SESSION_REJECTED_EVENT,
    WebSocketSignalingService,
)

CANONICAL_SLICES = {
    "channel_ingress",
    "end_of_turn",
    "stt",
    "backend_first_token",
    "tts_first_audio",
    "channel_egress",
}


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

    def build_session(self, transport, envelope, telemetry):
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
    def spawn(self, coro):
        coro.close()
        return object()

    def run(self, coro, *, timeout=None):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


class _FakeWebSocket:
    class _Req:
        def __init__(self, path):
            self.path = path

    def __init__(self, path="/"):
        self.request = self._Req(path)


def _build_started_service(telemetry):
    transport = _FakeTransport()

    def transport_builder(host, port, *, sample_rate, serializer, allowed_origins, on_client_rejected=None):
        return transport

    service = WebSocketSignalingService(
        factory=_FakeFactory(_FakeSession()),
        loop=_FakeLoop(),
        transport_builder=transport_builder,
    )
    service._telemetry_factory = lambda: telemetry
    service.start()
    return service, transport


@given("a started WebSocket signaling service with one connected client")
def step_started_with_one_client(context):
    context.telemetry = TelemetryRecorder()
    context.service, context.transport = _build_started_service(context.telemetry)
    asyncio.run(context.transport.handlers["on_client_connected"](context.transport, _FakeWebSocket()))


@when("an extra browser opens a wss voice connection")
def step_extra_client(context):
    # The socle refuses the extra concurrent client (WS 1013) and fires the callback.
    asyncio.run(context.service._on_client_rejected(_FakeWebSocket()))


@then("it is refused with the single-client capacity reason and no crash")
def step_refused_reason(context):
    rejected = [e for e in context.telemetry.events() if e.name == SESSION_REJECTED_EVENT]
    assert len(rejected) == 1, rejected
    assert rejected[0].attributes["reason"] == REASON_SINGLE_CLIENT, rejected[0].attributes


@then("an active-session gauge and a refusal event are recorded")
def step_gauge_and_event(context):
    gauges = [m for m in context.telemetry.metrics() if m.name == ACTIVE_SESSIONS_METRIC]
    assert any(g.attributes["outcome"] == "rejected" for g in gauges), gauges
    assert any(e.name == SESSION_REJECTED_EVENT for e in context.telemetry.events())


@given("a completed wss voice turn with only some slices measured")
def step_partial_turn(context):
    context.telemetry = TelemetryRecorder()
    context.telemetry.span("voice.end_of_turn", 120.0, correlation_id="corr-ws")
    context.telemetry.span("stt.request", 300.0, correlation_id="corr-ws")


@when("the per-call telemetry is dumped")
def step_dump_payload(context):
    context.payload = build_payload(context.telemetry)


@then("every canonical journey slice is present under one correlation id")
def step_all_slices_present(context):
    slices = context.payload["pipeline_timing"]["slices"]
    names = {s["slice"] for s in slices}
    assert CANONICAL_SLICES <= names, names


@then("a slice with no span is marked measured false, never omitted")
def step_missing_marked(context):
    by_name = {s["slice"]: s for s in context.payload["pipeline_timing"]["slices"]}
    assert by_name["backend_first_token"]["measured"] is False, by_name["backend_first_token"]
    assert by_name["channel_egress"]["measured"] is False, by_name["channel_egress"]
    assert by_name["end_of_turn"]["measured"] is True, by_name["end_of_turn"]
