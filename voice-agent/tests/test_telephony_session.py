"""Integration test for the telephony session handler (turn -> answer loop)."""

import asyncio
import base64
import json

import pytest
from unittest.mock import AsyncMock, patch

from agent.audio_codec import mulaw_encode_sample
from agent.gradium_stt import SttResult
from agent import telephony


class FakeWebSocket:
    """Async-iterable fake Twilio websocket capturing sent frames."""

    def __init__(self, inbound: list[str]):
        self._inbound = inbound
        self.sent: list[str] = []

    def __aiter__(self):
        self._it = iter(self._inbound)
        return self

    async def __anext__(self):
        # yield to the event loop so background response tasks can make progress,
        # mirroring real network frames arriving asynchronously over time
        await asyncio.sleep(0)
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration

    async def send(self, message):
        self.sent.append(message)


class FakeBackend:
    def __init__(self, tokens):
        self._tokens = tokens

    async def ask_stream(self, question, conversation_id):
        for tok in self._tokens:
            yield {"event": "chunk", "data": {"text": tok}}


def _media_frame(mulaw: bytes) -> str:
    payload = base64.b64encode(mulaw).decode("ascii")
    return json.dumps({"event": "media", "media": {"payload": payload}})


def _speech(ms: int) -> bytes:
    samples = int(8000 * ms / 1000)
    return bytes([mulaw_encode_sample(8000)]) * samples


def _silence(ms: int) -> bytes:
    samples = int(8000 * ms / 1000)
    return b"\xff" * samples


class FakeSttSession:
    def __init__(self, *args, **kwargs):
        pass

    def feed(self, audio):
        pass

    async def finalize(self):
        return SttResult(text="Ma box ne marche plus")


@pytest.mark.asyncio
async def test_call_produces_spoken_answer_after_turn():
    # GIVEN a call: start, speech, then enough trailing silence to end the turn
    inbound = [
        json.dumps({"event": "start", "start": {"streamSid": "MZ1"}}),
        _media_frame(_speech(300)),
        _media_frame(_silence(800)),
        # trailing silence frames keep the call "open" so the response task can
        # stream audio back before the stream stops (as happens on a real call)
        *[_media_frame(_silence(40)) for _ in range(15)],
        json.dumps({"event": "stop"}),
    ]
    ws = FakeWebSocket(inbound)
    backend = FakeBackend(["Bonjour, ", "redemarrez votre box."])

    with patch.object(telephony, "create_stt_session", FakeSttSession), \
         patch.object(telephony, "synthesize_speech",
                      new=AsyncMock(return_value=b"\x01\x02\x03")):
        # WHEN the session is handled
        await telephony.handle_twilio_client(ws, backend, "key", "voice", "fr")

    # THEN at least one mu-law media frame was streamed back to the caller
    media_frames = [json.loads(m) for m in ws.sent]
    assert any(f["event"] == "media" and f["streamSid"] == "MZ1" for f in media_frames)


@pytest.mark.asyncio
async def test_no_answer_when_only_silence():
    # GIVEN a call with no speech, only silence
    inbound = [
        json.dumps({"event": "start", "start": {"streamSid": "MZ2"}}),
        _media_frame(_silence(1000)),
        json.dumps({"event": "stop"}),
    ]
    ws = FakeWebSocket(inbound)
    backend = FakeBackend(["unused"])

    with patch.object(telephony, "create_stt_session", FakeSttSession), \
         patch.object(telephony, "synthesize_speech",
                      new=AsyncMock(return_value=b"\x01")):
        # WHEN handled
        await telephony.handle_twilio_client(ws, backend, "key", "voice", "fr")

    # THEN no audio is sent (turn never ended)
    assert ws.sent == []
