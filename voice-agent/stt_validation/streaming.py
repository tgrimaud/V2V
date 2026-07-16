"""Async streaming STT seam (TASK-STT-010).

Moves the STT path from whole-utterance *batch* transcription to *incremental*
transcription over Gradium's WebSocket ASR (`wss://api.gradium.ai/api/speech/asr`),
so partial transcripts arrive while the customer is still speaking and the final
transcript lands ~0.8 s after end-of-turn instead of paying the full clip-length
processing cost (see `docs/qa/stt-010-streaming-stt-spike.md`).

The WebSocket is injectable (duck-typed `WebSocketLike` via a `Connector`) so unit
tests never touch the network and the module carries no hard `websockets` import at
call sites other than the default connector. The API key is never placed in an
exception message, log or telemetry attribute. The batch `SttProvider` (REST) stays
untouched for fixtures/offline dev.
"""

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

DEFAULT_MODEL = "default"
DEFAULT_LANGUAGE = "fr"
DEFAULT_INPUT_FORMAT = "pcm_16000"
GRADIUM_STT_WS_URL = "wss://api.gradium.ai/api/speech/asr"


@dataclass(frozen=True)
class PartialTranscript:
    """An incremental transcript fragment emitted while the customer speaks."""

    text: str
    start_s: float | None = None


@dataclass(frozen=True)
class FinalTranscript:
    """The consolidated transcript, emitted once after end-of-turn."""

    text: str


class StreamingSttError(RuntimeError):
    """Streaming STT failed. The message is safe to surface (never carries the key)."""


class WebSocketLike(Protocol):
    """Minimal duck-typed WebSocket (both `websockets` and the test fake satisfy it)."""

    async def send(self, message: str) -> None: ...

    async def recv(self) -> str: ...

    async def close(self) -> None: ...


# (url, headers) -> awaitable WebSocketLike
Connector = Callable[[str, dict[str, str]], Awaitable[WebSocketLike]]


class GradiumStreamingSttProvider:
    name = "gradium-stt-streaming"

    def __init__(
        self,
        api_key: str,
        *,
        language: str = DEFAULT_LANGUAGE,
        input_format: str = DEFAULT_INPUT_FORMAT,
        model_name: str = DEFAULT_MODEL,
        url: str = GRADIUM_STT_WS_URL,
        connector: Connector | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Gradium API key is required")
        self._api_key = api_key
        self._language = language
        self._input_format = input_format
        self._model_name = model_name
        self._url = url
        self._connector = connector or _websockets_connector

    async def open(self) -> "GradiumStreamingSession":
        """Connect, send the setup message and return a live streaming session."""
        websocket = await self._connector(self._url, {"x-api-key": self._api_key})
        session = GradiumStreamingSession(
            websocket,
            model_name=self._model_name,
            input_format=self._input_format,
            language=self._language,
        )
        await session.start()
        return session


class GradiumStreamingSession:
    """A single streaming turn: push audio, receive partials, finalize on end-of-turn.

    Iterate the session (`async for msg in session`) to receive `PartialTranscript`
    fragments as they arrive and a single terminal `FinalTranscript`. `send_audio`
    pushes raw PCM chunks; `finish` flushes and closes the turn.
    """

    def __init__(
        self,
        websocket: WebSocketLike,
        *,
        model_name: str,
        input_format: str,
        language: str,
    ) -> None:
        self._ws = websocket
        self._setup = {
            "type": "setup",
            "model_name": model_name,
            "input_format": input_format,
            "json_config": {"language": language},
        }
        self._queue: asyncio.Queue = asyncio.Queue()
        self._parts: list[str] = []
        self._flush_id = 0
        self._receiver: asyncio.Task | None = None

    async def start(self) -> None:
        await self._ws.send(json.dumps(self._setup))
        self._receiver = asyncio.create_task(self._receive_loop())

    async def send_audio(self, pcm: bytes) -> None:
        payload = base64.b64encode(pcm).decode("ascii")
        await self._ws.send(json.dumps({"type": "audio", "audio": payload}))

    async def finish(self) -> None:
        """Flush pending audio and signal end-of-stream so the final transcript lands."""
        self._flush_id += 1
        await self._ws.send(json.dumps({"type": "flush", "flush_id": self._flush_id}))
        await self._ws.send(json.dumps({"type": "end_of_stream"}))

    async def aclose(self) -> None:
        if self._receiver is not None:
            self._receiver.cancel()
        await self._ws.close()

    def __aiter__(self) -> "GradiumStreamingSession":
        return self

    async def __anext__(self) -> PartialTranscript | FinalTranscript:
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        if isinstance(item, BaseException):
            raise item
        return item

    async def _receive_loop(self) -> None:
        try:
            while True:
                if await self._handle_message(await self._ws.recv()):
                    return
        except asyncio.CancelledError:
            raise
        except Exception:  # transport drop mid-turn -> surface via the queue, don't hang
            await self._queue.put(StreamingSttError("Streaming STT connection failed"))
            await self._queue.put(None)

    async def _handle_message(self, raw: str) -> bool:
        """Route one server message; return True when the stream is terminal."""
        message = _parse_message(raw)
        kind = message.get("type")
        if kind == "text":
            await self._emit_partial(message)
        elif kind == "end_of_stream":
            await self._emit_final()
            return True
        elif kind == "error":
            await self._queue.put(StreamingSttError("Streaming STT reported an error"))
            await self._queue.put(None)
            return True
        return False

    async def _emit_partial(self, message: dict) -> None:
        text = str(message.get("text", ""))
        if text:
            self._parts.append(text)
            await self._queue.put(PartialTranscript(text, message.get("start_s")))

    async def _emit_final(self) -> None:
        transcript = " ".join(part for part in self._parts if part).strip()
        await self._queue.put(FinalTranscript(transcript))
        await self._queue.put(None)


def _parse_message(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StreamingSttError("Streaming STT returned an unparsable message") from exc


async def _websockets_connector(url: str, headers: dict[str, str]) -> WebSocketLike:
    import websockets  # imported lazily so tests need no network stack

    return await websockets.connect(url, additional_headers=headers, max_size=None)
