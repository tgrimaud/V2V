"""Tests for the async streaming TTS seam (TASK-WEB-004).

Drives `GradiumStreamingTtsProvider` / `GradiumStreamingTtsSession` with an in-memory
fake WebSocket (no network), proving:
- audio chunks stream in order and stop on end_of_stream;
- the setup message carries voice/format but never the API key;
- the key travels only in the connect header;
- `synthesize` sends the text then end_of_stream; empty text is rejected;
- interleaved `text`/`ready` echoes are ignored;
- server `error`, an unparsable frame and a mid-stream transport drop surface as
  `StreamingTtsError`.
"""

import asyncio
import base64
import json
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from tts_synthesis.providers import EmptyTextError  # noqa: E402
from tts_synthesis.streaming import (  # noqa: E402
    AudioChunk,
    GradiumStreamingTtsProvider,
    StreamingTtsError,
)


class FakeWebSocket:
    """Scripted WebSocket: replays server frames, records what the client sent."""

    def __init__(self, server_frames, *, raise_after=False):
        self.sent = []
        self.closed = False
        self._incoming = asyncio.Queue()
        for frame in server_frames:
            self._incoming.put_nowait(frame)
        self._raise_after = raise_after

    async def send(self, message):
        self.sent.append(json.loads(message))

    async def recv(self):
        if self._incoming.empty() and self._raise_after:
            raise ConnectionError("socket dropped")
        return await self._incoming.get()

    async def close(self):
        self.closed = True


def _frame(payload) -> str:
    return payload if isinstance(payload, str) else json.dumps(payload)


def _connector_for(websocket, captured):
    async def connector(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return websocket

    return connector


async def _open(server_frames, *, raise_after=False, captured=None):
    websocket = FakeWebSocket([_frame(f) for f in server_frames], raise_after=raise_after)
    provider = GradiumStreamingTtsProvider(
        "secret-key",
        voice_id="voice-x",
        output_format="pcm_16000",
        connector=_connector_for(websocket, captured if captured is not None else {}),
    )
    session = await provider.open()
    return websocket, session


async def _collect(session) -> list[AudioChunk]:
    return [chunk async for chunk in session.stream()]


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


class StreamingTtsProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_streams_audio_chunks_in_order_until_end(self):
        # GIVEN a server that streams two audio chunks then end_of_stream
        frames = [
            {"type": "ready", "sample_rate": 16000},
            {"type": "audio", "audio": _b64(b"\x01\x02")},
            {"type": "text", "text": "echo"},  # interleaved token echo -> ignored
            {"type": "audio", "audio": _b64(b"\x03\x04")},
            {"type": "end_of_stream"},
        ]
        _, session = await _open(frames)
        await session.synthesize("bonjour")
        # WHEN the client drains the audio stream
        chunks = await _collect(session)
        # THEN chunks arrive in order and the token echo is not audio
        self.assertEqual(chunks, [AudioChunk(b"\x01\x02"), AudioChunk(b"\x03\x04")])

    async def test_setup_sent_first_without_key(self):
        # GIVEN a minimal successful stream
        websocket, session = await _open([{"type": "end_of_stream"}])
        await session.synthesize("salut")
        await _collect(session)
        # THEN the first client message is the setup with voice/format, no key
        setup = websocket.sent[0]
        self.assertEqual(setup["type"], "setup")
        self.assertEqual(setup["voice_id"], "voice-x")
        self.assertEqual(setup["output_format"], "pcm_16000")
        self.assertNotIn("secret-key", json.dumps(setup))

    async def test_api_key_travels_only_in_connect_header(self):
        # GIVEN the connector records its headers
        captured: dict = {}
        websocket, session = await _open([{"type": "end_of_stream"}], captured=captured)
        await session.synthesize("hi")
        await _collect(session)
        # THEN the key is in the header and nowhere in the sent frames
        self.assertEqual(captured["headers"], {"x-api-key": "secret-key"})
        self.assertNotIn("secret-key", json.dumps(websocket.sent))

    async def test_synthesize_sends_text_then_end_of_stream(self):
        # GIVEN an open session
        websocket, session = await _open([{"type": "end_of_stream"}])
        # WHEN the client synthesizes text
        await session.synthesize("bonjour le monde")
        # THEN a text frame then an end_of_stream frame were sent (after setup)
        kinds = [m["type"] for m in websocket.sent]
        self.assertEqual(kinds, ["setup", "text", "end_of_stream"])
        text_frame = next(m for m in websocket.sent if m["type"] == "text")
        self.assertEqual(text_frame["text"], "bonjour le monde")

    async def test_empty_text_rejected(self):
        # GIVEN an open session
        _, session = await _open([{"type": "end_of_stream"}])
        # THEN synthesizing empty/whitespace text raises EmptyTextError (UNAVAILABLE)
        with self.assertRaises(EmptyTextError):
            await session.synthesize("   ")

    async def test_empty_audio_payload_ignored(self):
        # GIVEN an audio frame with no payload followed by a real one
        frames = [
            {"type": "audio", "audio": ""},
            {"type": "audio", "audio": _b64(b"\x05\x06")},
            {"type": "end_of_stream"},
        ]
        _, session = await _open(frames)
        await session.synthesize("x")
        chunks = await _collect(session)
        # THEN only the non-empty chunk is emitted
        self.assertEqual(chunks, [AudioChunk(b"\x05\x06")])

    async def test_server_error_surfaces_as_streaming_error(self):
        # GIVEN the server reports an error mid-stream
        frames = [{"type": "audio", "audio": _b64(b"\x01")}, {"type": "error", "message": "boom"}]
        _, session = await _open(frames)
        await session.synthesize("x")
        # THEN draining the stream raises a safe StreamingTtsError
        with self.assertRaises(StreamingTtsError):
            await _collect(session)

    async def test_credits_error_is_mapped_safely(self):
        # GIVEN the server reports exhausted credits
        frames = [{"type": "error", "code": 1011, "message": "Insufficient credits"}]
        _, session = await _open(frames)
        await session.synthesize("x")
        # THEN the error message is the safe mapped text, never the raw payload
        with self.assertRaises(StreamingTtsError) as ctx:
            await _collect(session)
        self.assertEqual(str(ctx.exception), "Streaming TTS credits exhausted")

    async def test_transport_drop_surfaces_as_streaming_error(self):
        # GIVEN the socket drops before end_of_stream
        _, session = await _open([{"type": "audio", "audio": _b64(b"\x01")}], raise_after=True)
        await session.synthesize("x")
        # THEN the drop surfaces as StreamingTtsError, not a hang
        with self.assertRaises(StreamingTtsError):
            await asyncio.wait_for(_collect(session), timeout=2.0)

    async def test_unparsable_message_surfaces_error(self):
        # GIVEN the server sends a non-JSON frame
        _, session = await _open(["not-json"])
        await session.synthesize("x")
        # THEN it surfaces as a StreamingTtsError
        with self.assertRaises(StreamingTtsError):
            await _collect(session)

    async def test_empty_api_key_rejected(self):
        # GIVEN no API key
        with self.assertRaises(ValueError):
            GradiumStreamingTtsProvider("")

    async def test_empty_voice_id_rejected(self):
        # GIVEN no voice id
        with self.assertRaises(ValueError):
            GradiumStreamingTtsProvider("secret-key", voice_id="")


if __name__ == "__main__":
    unittest.main()
