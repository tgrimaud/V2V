"""Behave steps for the external browser WebSocket audio transport (TASK-WEB-026)."""

import asyncio
import json
import sys

from behave import given, then, when
from pipecat.frames.frames import InputAudioRawFrame, InterruptionFrame

from web_voice.websocket_framing import ControlType, WebSocketAudioSerializer
from web_voice.websocket_support import build_websocket_audio_transport


def _run(coro):
    return asyncio.run(coro)


@given("the voice bridge builds the WebSocket audio transport")
def step_build_transport(context):
    context.fastapi_before = {m for m in sys.modules if m == "fastapi" or m.startswith("fastapi.")}
    context.transport = build_websocket_audio_transport("127.0.0.1", 8091)


@then("the transport is the websockets-based server variant")
def step_transport_is_websockets(context):
    assert context.transport.__class__.__module__ == "pipecat.transports.websocket.server"


@then("building it requires no FastAPI import")
def step_no_fastapi(context):
    fastapi_after = {m for m in sys.modules if m == "fastapi" or m.startswith("fastapi.")}
    assert context.fastapi_before == fastapi_after, "building the socle pulled in FastAPI"


@given("an open WebSocket voice connection")
def step_open_connection(context):
    context.serializer = WebSocketAudioSerializer()
    _run(context.serializer.deserialize(json.dumps({"type": ControlType.OPEN})))
    assert context.serializer.is_open


@when("the client sends a binary PCM16 16 kHz audio frame")
def step_send_audio(context):
    context.audio_result = _run(context.serializer.deserialize(b"\x01\x02" * 160))


@then("the server treats it as customer audio")
def step_audio_is_input(context):
    assert isinstance(context.audio_result, InputAudioRawFrame)
    assert context.audio_result.sample_rate == 16000
    assert context.audio_result.num_channels == 1


@when("the client sends a JSON control frame")
def step_send_control(context):
    context.control_result = _run(
        context.serializer.deserialize(json.dumps({"type": ControlType.LANGUAGE, "language": "fr"}))
    )


@then("the server treats it as a control message, never as audio")
def step_control_not_audio(context):
    assert not isinstance(context.control_result, InputAudioRawFrame)
    assert context.serializer.selected_language == "fr"


@when("the client sends a barge-in control frame")
def step_send_barge_in(context):
    context.barge_in_result = _run(
        context.serializer.deserialize(json.dumps({"type": ControlType.BARGE_IN}))
    )


@then("the server raises an interruption on the voice pipeline")
def step_interruption(context):
    assert isinstance(context.barge_in_result, InterruptionFrame)
