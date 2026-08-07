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
from typing import Awaitable, Callable, Protocol, runtime_checkable

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


@runtime_checkable
class StreamingSttSession(Protocol):
    """A single live streaming-STT turn (TASK-WEB-023).

    The explicit contract the WebRTC hot path (`StreamingSttProcessor`) drives, so any
    vendor — not just Gradium — can back it: push audio, drain partials as they stream,
    finalize on end-of-turn, then close. `GradiumStreamingSession` is one implementation.
    """

    async def send_audio(self, pcm: bytes) -> None: ...

    def poll_partials(self) -> list[PartialTranscript]: ...

    async def finish(self) -> None: ...

    async def wait_final(self) -> FinalTranscript: ...

    async def aclose(self) -> None: ...


@runtime_checkable
class StreamingSttProvider(Protocol):
    """Opens `StreamingSttSession`s for the low-latency voice path (TASK-WEB-023).

    Breaks the Gradium lock on the streaming (latency-critical) STT path: the runtime and
    the provider factory depend on this protocol, not on `GradiumStreamingSttProvider`.
    A conforming provider exposes a stable `name` and an async `open()`.
    """

    name: str

    async def open(self) -> StreamingSttSession: ...


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

    A background receiver consumes server messages: `poll_partials()` drains the
    `PartialTranscript` fragments seen so far (non-blocking, so the caller can push
    them as they stream while it keeps feeding audio), and `wait_final()` blocks
    until the terminal `FinalTranscript` (or raises `StreamingSttError` on a server
    error / mid-turn transport drop). `send_audio` pushes raw PCM; `finish` flushes
    and signals end-of-stream so the final transcript lands.
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
        self._pending: list[PartialTranscript] = []
        self._parts: list[str] = []
        self._final: FinalTranscript | None = None
        self._error: StreamingSttError | None = None
        self._done = asyncio.Event()
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

    def poll_partials(self) -> list[PartialTranscript]:
        """Drain the partials received since the last poll (non-blocking)."""
        drained, self._pending = self._pending, []
        return drained

    @property
    def done(self) -> bool:
        return self._done.is_set()

    async def wait_final(self) -> FinalTranscript:
        await self._done.wait()
        if self._error is not None:
            raise self._error
        return self._final or FinalTranscript("")

    async def aclose(self) -> None:
        if self._receiver is not None:
            self._receiver.cancel()
        await self._ws.close()

    async def _receive_loop(self) -> None:
        try:
            while not self._handle_message(await self._ws.recv()):
                pass
        except asyncio.CancelledError:
            raise
        except StreamingSttError as exc:  # unparsable server frame
            self._fail(exc)
        except Exception:  # transport drop mid-turn -> surface, don't hang
            self._fail(StreamingSttError("Streaming STT connection failed"))

    def _handle_message(self, raw: str) -> bool:
        """Route one server message; return True when the turn is terminal for us."""
        message = _parse_message(raw)
        kind = message.get("type")
        if kind == "text":
            self._add_partial(message)
        elif kind == "flushed" and self._flush_id > 0:
            # Finalize on the flush acknowledgement rather than blocking on the terminal
            # `end_of_stream`. TASK-STT-013 spike (docs/qa/stt-013-finalize-tail-spike.md):
            # every pending partial has been emitted by the time `flushed` lands (~350 ms
            # after our end-of-turn flush), so this is the *full* transcript ~430 ms
            # sooner than `end_of_stream`, with no word loss — the primary lever to meet
            # the ADR-0018 `time_to_first_audio` gate. Guarded by `_flush_id > 0` so a
            # stray ack before our end-of-turn flush can never finalize early.
            self._finalize_from_parts()
            return True
        elif kind == "end_of_stream":
            # Fallback terminal: a provider that never sends `flushed` still finalizes.
            self._finalize_from_parts()
            return True
        elif kind == "error":
            self._fail(StreamingSttError("Streaming STT reported an error"))
            return True
        return False

    def _finalize_from_parts(self) -> None:
        self._final = FinalTranscript(" ".join(p for p in self._parts if p).strip())
        self._done.set()

    def _add_partial(self, message: dict) -> None:
        text = str(message.get("text", ""))
        if text:
            self._parts.append(text)
            self._pending.append(PartialTranscript(text, message.get("start_s")))

    def _fail(self, error: StreamingSttError) -> None:
        self._error = error
        self._done.set()


def _parse_message(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StreamingSttError("Streaming STT returned an unparsable message") from exc


async def _websockets_connector(url: str, headers: dict[str, str]) -> WebSocketLike:
    import websockets  # imported lazily so tests need no network stack

    return await websockets.connect(url, additional_headers=headers, max_size=None)
