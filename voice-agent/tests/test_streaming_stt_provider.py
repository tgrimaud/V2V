"""Tests for the async streaming STT seam (TASK-STT-010).

Drives `GradiumStreamingSttProvider` / `GradiumStreamingSession` with an in-memory
fake WebSocket (no network), proving:
- partials stream in order and the final transcript is the joined parts;
- the setup message carries language/format but never the API key;
- the key travels only in the connect header;
- `send_audio` base64-encodes PCM; `finish` flushes then ends the stream;
- server `error` and a mid-turn transport drop surface as `StreamingSttError`.
"""

import asyncio
import json
import sys
import unittest
from pathlib import Path

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from stt_validation.streaming import (  # noqa: E402
    FinalTranscript,
    GradiumStreamingSttProvider,
    PartialTranscript,
    StreamingSttError,
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


class FlushDrivenWebSocket:
    """WebSocket that emits `pre` frames immediately, then enqueues `post` frames only
    once the client sends its `flush` — mirrors Gradium, where `flushed` /
    `end_of_stream` arrive only after our end-of-turn flush. This guarantees the
    session's `flush_id` is set before `flushed` is delivered (real-flow ordering),
    so the test exercises the TASK-STT-013 finalize-on-`flushed` path deterministically.
    """

    def __init__(self, pre, post):
        self.sent = []
        self.closed = False
        self._incoming = asyncio.Queue()
        for frame in pre:
            self._incoming.put_nowait(_frame(frame))
        self._post = [_frame(frame) for frame in post]

    async def send(self, message):
        msg = json.loads(message)
        self.sent.append(msg)
        if msg.get("type") == "flush":
            for frame in self._post:
                self._incoming.put_nowait(frame)

    async def recv(self):
        return await self._incoming.get()

    async def close(self):
        self.closed = True

    @property
    def pending_frames(self) -> int:
        return self._incoming.qsize()


def _connector_for(websocket, captured):
    async def connector(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return websocket

    return connector


async def _open(server_frames, *, raise_after=False, captured=None):
    websocket = FakeWebSocket([_frame(f) for f in server_frames], raise_after=raise_after)
    provider = GradiumStreamingSttProvider(
        "secret-key",
        language="fr",
        input_format="pcm_16000",
        connector=_connector_for(websocket, captured if captured is not None else {}),
    )
    session = await provider.open()
    return websocket, session


async def _collect(session) -> tuple[list, FinalTranscript]:
    """Wait for the terminal final, then drain every partial the receiver queued."""
    final = await session.wait_final()
    return session.poll_partials(), final


class StreamingSttProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_streams_partials_then_final_joined(self):
        # GIVEN a server that emits two text fragments then end_of_stream
        frames = [
            {"type": "ready", "frame_size": 1920},
            {"type": "text", "text": "bonjour", "start_s": 0.5},
            {"type": "text", "text": "le monde", "start_s": 1.0},
            {"type": "end_of_stream"},
        ]
        _, session = await _open(frames)
        # WHEN the client waits for the final and drains partials
        partials, final = await _collect(session)
        # THEN partials arrive in order and the final is the joined parts
        self.assertEqual(partials[0], PartialTranscript("bonjour", 0.5))
        self.assertEqual(partials[1], PartialTranscript("le monde", 1.0))
        self.assertEqual(final, FinalTranscript("bonjour le monde"))

    async def test_setup_sent_first_without_key(self):
        # GIVEN a minimal successful stream
        captured: dict = {}
        websocket, session = await _open(
            [{"type": "end_of_stream"}], captured=captured
        )
        await session.wait_final()
        # THEN the first client message is the setup with format/language, no key
        setup = websocket.sent[0]
        self.assertEqual(setup["type"], "setup")
        self.assertEqual(setup["input_format"], "pcm_16000")
        self.assertEqual(setup["json_config"], {"language": "fr"})
        self.assertNotIn("secret-key", json.dumps(setup))

    async def test_api_key_travels_only_in_connect_header(self):
        # GIVEN the connector records its headers
        captured: dict = {}
        _, session = await _open([{"type": "end_of_stream"}], captured=captured)
        await session.wait_final()
        # THEN the key is in the header and nowhere in the sent frames
        self.assertEqual(captured["headers"], {"x-api-key": "secret-key"})

    async def test_send_audio_base64_then_finish_flushes(self):
        # GIVEN an open session
        websocket, session = await _open([{"type": "end_of_stream"}])
        # WHEN the client sends PCM and finishes the turn
        await session.send_audio(b"\x01\x02\x03\x04")
        await session.finish()
        await session.wait_final()
        # THEN the audio frame is base64 and finish emits flush then end_of_stream
        audio_frames = [m for m in websocket.sent if m.get("type") == "audio"]
        self.assertEqual(audio_frames[0]["audio"], "AQIDBA==")
        kinds = [m["type"] for m in websocket.sent]
        self.assertEqual(kinds[-2:], ["flush", "end_of_stream"])

    async def test_empty_text_fragment_ignored(self):
        # GIVEN a text frame with no content followed by a real one
        frames = [
            {"type": "text", "text": ""},
            {"type": "text", "text": "facture"},
            {"type": "end_of_stream"},
        ]
        _, session = await _open(frames)
        partials, final = await _collect(session)
        # THEN only the non-empty fragment is emitted and joined
        self.assertEqual(partials, [PartialTranscript("facture", None)])
        self.assertEqual(final, FinalTranscript("facture"))

    async def test_server_error_surfaces_as_streaming_error(self):
        # GIVEN the server reports an error mid-turn
        frames = [{"type": "text", "text": "hi"}, {"type": "error", "message": "boom"}]
        _, session = await _open(frames)
        # THEN waiting for the final raises a safe StreamingSttError
        with self.assertRaises(StreamingSttError):
            await session.wait_final()

    async def test_transport_drop_surfaces_as_streaming_error(self):
        # GIVEN the socket drops before end_of_stream
        _, session = await _open([{"type": "text", "text": "hi"}], raise_after=True)
        # THEN the drop surfaces as StreamingSttError, not a hang
        with self.assertRaises(StreamingSttError):
            await asyncio.wait_for(session.wait_final(), timeout=2.0)

    async def test_unparsable_message_surfaces_error(self):
        # GIVEN the server sends a non-JSON frame
        _, session = await _open(["not-json"])
        # THEN it surfaces as a StreamingSttError
        with self.assertRaises(StreamingSttError):
            await session.wait_final()

    async def test_finalizes_on_flushed_not_end_of_stream(self):
        # GIVEN partials during speech; the server acks our end-of-turn flush
        # (`flushed`) and would only later send the terminal `end_of_stream`
        websocket = FlushDrivenWebSocket(
            pre=[
                {"type": "text", "text": "bonjour"},
                {"type": "text", "text": "le monde"},
            ],
            post=[{"type": "flushed", "flush_id": 1}, {"type": "end_of_stream"}],
        )
        provider = GradiumStreamingSttProvider(
            "secret-key", connector=_connector_for(websocket, {})
        )
        session = await provider.open()
        await session.send_audio(b"\x01\x02")
        await session.finish()
        # WHEN the client waits for the final
        final = await asyncio.wait_for(session.wait_final(), timeout=2.0)
        # THEN it finalizes on `flushed` with the FULL transcript (no word loss)...
        self.assertEqual(final, FinalTranscript("bonjour le monde"))
        # ...and never consumed the terminal end_of_stream (still queued) — proving the
        # ~430 ms end_of_stream wait was skipped (TASK-STT-013).
        self.assertEqual(websocket.pending_frames, 1)

    async def test_end_of_stream_still_finalizes_when_no_flushed(self):
        # GIVEN a provider variant that never sends `flushed`
        frames = [
            {"type": "text", "text": "bonjour"},
            {"type": "end_of_stream"},
        ]
        _, session = await _open(frames)
        # WHEN the client waits for the final
        final = await session.wait_final()
        # THEN end_of_stream is still an accepted terminal (safe fallback)
        self.assertEqual(final, FinalTranscript("bonjour"))

    async def test_empty_api_key_rejected(self):
        # GIVEN no API key
        with self.assertRaises(ValueError):
            GradiumStreamingSttProvider("")


if __name__ == "__main__":
    unittest.main()
