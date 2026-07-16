"""Async streaming TTS seam (TASK-WEB-004).

Moves the TTS path from *batch* synthesis (synthesize the whole clip, then play) to
*incremental* playback over Gradium's WebSocket TTS
(`wss://api.gradium.ai/api/speech/tts`), so the customer hears the first words on the
first synthesized audio chunk instead of waiting for the full clip. The spike
(`docs/qa/gradium-tts-contract.md`) measured first-chunk latency ~340 ms vs ~1.59 s
for the whole 4.24 s clip — a ~4.7x cut on time-to-first-audio.

Symmetric mirror of `stt_validation/streaming.py` for the voice-out side. The
WebSocket is injectable (duck-typed `WebSocketLike` via a `Connector`) so unit tests
never touch the network and the module carries no hard `websockets` import at call
sites other than the default connector. The API key is never placed in an exception
message, log or telemetry attribute. The batch `TtsProvider` (`GradiumTtsProvider`)
stays untouched for fixtures/offline dev and as the fallback.

Contract (spike ST-1): connect with `x-api-key` -> send `setup` -> (server `ready`) ->
send `text` + `end_of_stream` -> collect `audio` (base64 PCM16) chunks until
`end_of_stream`; interleaved `text` echoes are ignored, `error` frames surface safely.
"""

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol

from .providers import DEFAULT_AUDIO_FORMAT, EmptyTextError

DEFAULT_MODEL = "default"
# `voice_id=default` is rejected by Gradium ("Embeddings not found"); a real catalog
# voice id is required. Elise (FR) is the project default (spike ST-1).
DEFAULT_VOICE_ID = "b35yykvVppLXyw_l"
DEFAULT_OUTPUT_FORMAT = DEFAULT_AUDIO_FORMAT  # pcm_16000 (PCM16 mono 16 kHz)
GRADIUM_TTS_WS_URL = "wss://api.gradium.ai/api/speech/tts"
DEFAULT_CHUNK_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class AudioChunk:
    """One incremental PCM16 audio fragment streamed while synthesis is ongoing."""

    pcm: bytes


class StreamingTtsError(RuntimeError):
    """Streaming TTS failed. The message is safe to surface (never carries the key)."""


class WebSocketLike(Protocol):
    """Minimal duck-typed WebSocket (both `websockets` and the test fake satisfy it)."""

    async def send(self, message: str) -> None: ...

    async def recv(self) -> str: ...

    async def close(self) -> None: ...


# (url, headers) -> awaitable WebSocketLike
Connector = Callable[[str, dict[str, str]], Awaitable[WebSocketLike]]


class GradiumStreamingTtsProvider:
    name = "gradium-tts-streaming"

    def __init__(
        self,
        api_key: str,
        *,
        voice_id: str = DEFAULT_VOICE_ID,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        model_name: str = DEFAULT_MODEL,
        url: str = GRADIUM_TTS_WS_URL,
        chunk_timeout_s: float = DEFAULT_CHUNK_TIMEOUT_S,
        connector: Connector | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Gradium API key is required")
        if not voice_id:
            raise ValueError("Gradium voice_id is required")
        self._api_key = api_key
        self._voice_id = voice_id
        self._output_format = output_format
        self._model_name = model_name
        self._url = url
        self._chunk_timeout_s = chunk_timeout_s
        self._connector = connector or _websockets_connector

    @property
    def audio_format(self) -> str:
        return self._output_format

    async def open(self) -> "GradiumStreamingTtsSession":
        """Connect, send the setup message and return a live streaming session."""
        websocket = await self._connector(self._url, {"x-api-key": self._api_key})
        session = GradiumStreamingTtsSession(
            websocket,
            model_name=self._model_name,
            voice_id=self._voice_id,
            output_format=self._output_format,
            chunk_timeout_s=self._chunk_timeout_s,
        )
        await session.start()
        return session


class GradiumStreamingTtsSession:
    """A single synthesis: send text, then stream audio chunks until end-of-stream.

    Unlike the STT session (bidirectional, interleaved), TTS is send-once /
    receive-many: `synthesize(text)` sends the text + end-of-stream, then `stream()`
    yields `AudioChunk`s as they arrive so the caller pushes them to playback
    incrementally. `stream()` returns on the terminal `end_of_stream`; a server
    `error`, an unparsable frame or a stalled socket surface as `StreamingTtsError`.
    """

    def __init__(
        self,
        websocket: WebSocketLike,
        *,
        model_name: str,
        voice_id: str,
        output_format: str,
        chunk_timeout_s: float = DEFAULT_CHUNK_TIMEOUT_S,
    ) -> None:
        self._ws = websocket
        self._setup = {
            "type": "setup",
            "model_name": model_name,
            "voice_id": voice_id,
            "output_format": output_format,
        }
        self._chunk_timeout_s = chunk_timeout_s

    async def start(self) -> None:
        await self._ws.send(json.dumps(self._setup))

    async def synthesize(self, text: str) -> None:
        """Send the text and signal end-of-stream so the server starts streaming audio."""
        if not text or not text.strip():
            raise EmptyTextError("No text to synthesize")
        await self._ws.send(json.dumps({"type": "text", "text": text}))
        await self._ws.send(json.dumps({"type": "end_of_stream"}))

    async def stream(self) -> AsyncIterator[AudioChunk]:
        """Yield PCM16 audio chunks as they arrive, until the terminal end-of-stream."""
        while True:
            chunk, terminal = self._handle_message(await self._recv())
            if chunk is not None:
                yield chunk
            if terminal:
                return

    async def aclose(self) -> None:
        await self._ws.close()

    async def _recv(self) -> str:
        try:
            return await asyncio.wait_for(self._ws.recv(), timeout=self._chunk_timeout_s)
        except asyncio.TimeoutError as exc:
            raise StreamingTtsError("Streaming TTS timed out waiting for audio") from exc
        except StreamingTtsError:
            raise
        except Exception as exc:  # transport drop mid-stream -> surface, don't hang
            raise StreamingTtsError("Streaming TTS connection failed") from exc

    def _handle_message(self, raw: str) -> tuple[AudioChunk | None, bool]:
        """Route one server message; return (audio chunk or None, is terminal)."""
        message = _parse_message(raw)
        kind = message.get("type")
        if kind == "audio":
            audio_b64 = message.get("audio")
            if audio_b64:
                return AudioChunk(base64.b64decode(audio_b64)), False
            return None, False
        if kind == "error":
            raise _protocol_error(message)
        if kind == "end_of_stream":
            return None, True
        # `ready` and interleaved `text` echoes are ignored (spike ST-1).
        return None, False


def _parse_message(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StreamingTtsError("Streaming TTS returned an unparsable message") from exc


def _protocol_error(message: dict[str, Any]) -> StreamingTtsError:
    code = message.get("code")
    text = str(message.get("message", "")).lower()
    if "credit" in text:
        return StreamingTtsError("Streaming TTS credits exhausted")
    if "embeddings not found" in text:
        return StreamingTtsError("Streaming TTS voice id is invalid")
    if code == 401 or "auth" in text:
        return StreamingTtsError("Streaming TTS authentication failed")
    return StreamingTtsError(f"Streaming TTS service error (code {code})")


async def _websockets_connector(url: str, headers: dict[str, str]) -> WebSocketLike:
    import websockets  # imported lazily so tests need no network stack

    return await websockets.connect(url, additional_headers=headers, max_size=None)
