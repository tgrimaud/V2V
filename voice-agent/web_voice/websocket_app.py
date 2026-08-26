"""aiohttp-native WebSocket voice transport + `GET /ws` handler (TASK-WEB-038, ADR-0047).

Slice 2 of the single-port unification. The interim path (`websocket_signaling.py`) runs
pipecat's `SingleClientWebsocketServerTransport`, which owns a `websockets` server on its
own port (`:8091`) and is capped at one client per listener. That transport **cannot share
aiohttp's listener**, so this module provides an aiohttp-native pipecat transport that
consumes an **already-upgraded** `aiohttp.web.WebSocketResponse` — the same shape as
pipecat's `FastAPIWebsocketTransport`, but built directly on `BaseInput/OutputTransport`
so it pulls **no FastAPI/starlette** (ADR-0022).

Each `GET /ws` connection is its own handler coroutine → its own transport → its own
`StreamingVoiceSession` (built by the unchanged `SessionFactory`, ADR-0043) awaited inline
on the aiohttp event loop. Concurrency is therefore natural: N connections = N sessions,
lifting the single-client cap; a configurable ceiling (`VOICE_MAX_WS_SESSIONS`) refuses
extra connections with WS close code 1013 (try again later), mirroring the interim refusal.

The wire framing (JSON control + binary PCM16/16 kHz) reuses `WebSocketAudioSerializer`, and
the per-slice telemetry (US-036) + capacity gauge/refusal events reuse the same names as the
interim path so a pilot chart spans both transports.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
import typing
import wave
from typing import Any, Awaitable, Callable

from aiohttp import WSMsgType, web
from pipecat.frames.frames import (
    CancelFrame,
    ClientConnectedFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InputTransportMessageFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
    StartFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.utils.security.allowed_origins import is_origin_allowed

from voice_common.telemetry import TelemetryRecorder

from .envelope import ChannelEnvelope
from .session_factory import SessionFactory
from .session_telemetry import log_telemetry
from .websocket_framing import WebSocketAudioSerializer
from .websocket_signaling import (
    ACTIVE_SESSIONS_METRIC,
    CLIENT_CONNECTED_EVENT,
    CLIENT_DISCONNECTED_EVENT,
    SESSION_REJECTED_EVENT,
    SESSION_STARTED_EVENT,
    WS_MAX_SESSIONS_ENV_VAR,
)

_logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 16000
WS_ROUTE = "/ws"
# The single-async-server target lifts the interim one-call cap. This is the async-path
# default ceiling; VOICE_MAX_WS_SESSIONS overrides it (used by both paths).
DEFAULT_MAX_WS_SESSIONS_ASYNC = 8
# WS close code for a refused connection (try again later) — same code the interim
# single-client socle used, so browsers keep the "try again shortly" behaviour.
WS_TRY_AGAIN_LATER = 1013
REASON_CAPACITY = "capacity"
_WS_CLOSE_TIMEOUT = 0.5


class AiohttpWebsocketParams(TransportParams):
    """Transport params carrying the frame serializer (mirrors the pipecat WS params)."""

    add_wav_header: bool = False
    serializer: FrameSerializer | None = None


class AiohttpWebsocketClient:
    """Wraps one already-upgraded `aiohttp.web.WebSocketResponse`.

    Abstracts the socket so the input/output transports below stay identical to
    pipecat's generic WS transports. A leave-counter (incremented by both input and
    output `start`, decremented by both teardowns) ensures the socket is closed only
    once both sides are done, never while one is still sending.
    """

    def __init__(
        self,
        websocket: web.WebSocketResponse,
        *,
        on_connected: Callable[[], Awaitable[None]] | None = None,
        on_disconnected: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._ws = websocket
        self._closing = False
        self._leave_counter = 0
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected

    async def setup(self, _frame: StartFrame) -> None:
        self._leave_counter += 1

    async def trigger_client_connected(self) -> None:
        if self._on_connected is not None:
            await self._on_connected()

    async def trigger_client_disconnected(self) -> None:
        if self._on_disconnected is not None:
            await self._on_disconnected()

    def receive(self) -> typing.AsyncIterator[bytes | str]:
        return _AiohttpMessageIterator(self._ws)

    async def send(self, data: str | bytes) -> None:
        try:
            if self._can_send():
                if isinstance(data, (bytes, bytearray)):
                    await self._ws.send_bytes(bytes(data))
                else:
                    await self._ws.send_str(data)
        except Exception as exc:  # noqa: BLE001 - a send race on a closing socket must not crash
            _logger.warning("aiohttp ws send failed: %s (%s)", exc.__class__.__name__, exc)

    async def disconnect(self) -> None:
        self._leave_counter -= 1
        if self._leave_counter > 0:
            return
        if self.is_connected and not self._closing:
            self._closing = True
            try:
                await asyncio.wait_for(self._ws.close(), timeout=_WS_CLOSE_TIMEOUT)
            except Exception:  # noqa: BLE001 - never block shutdown on a dead/slow peer
                _logger.debug("aiohttp ws close timed out; proceeding with shutdown")

    def _can_send(self) -> bool:
        return self.is_connected and not self._closing

    @property
    def is_connected(self) -> bool:
        return not self._ws.closed

    @property
    def is_closing(self) -> bool:
        return self._closing


class _AiohttpMessageIterator:
    """Async iterator yielding binary (bytes) / text (str) messages, stopping on close."""

    _DATA_TYPES = {WSMsgType.BINARY, WSMsgType.TEXT}

    def __init__(self, websocket: web.WebSocketResponse) -> None:
        self._ws = websocket

    def __aiter__(self) -> "_AiohttpMessageIterator":
        return self

    async def __anext__(self) -> bytes | str:
        while True:
            message = await self._ws.receive()
            if message.type in self._DATA_TYPES:
                return message.data
            # CLOSE / CLOSING / CLOSED / ERROR (and any non-data control) end the stream.
            raise StopAsyncIteration


class AiohttpWebsocketInputTransport(BaseInputTransport):
    """Reads WS messages, deserializes to frames and pushes them into the pipeline."""

    def __init__(self, transport, client: AiohttpWebsocketClient, params, **kwargs) -> None:
        super().__init__(params, **kwargs)
        self._transport = transport
        self._client = client
        self._params = params
        self._receive_task = None
        self._initialized = False

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        if self._initialized:
            return
        self._initialized = True
        await self._client.setup(frame)
        if self._params.serializer:
            await self._params.serializer.setup(frame)
        await self._client.trigger_client_connected()
        await self.push_frame(ClientConnectedFrame())
        if not self._receive_task:
            self._receive_task = self.create_task(self._receive_messages())
        await self.set_transport_ready(frame)

    async def _teardown(self) -> None:
        if self._receive_task:
            await self.cancel_task(self._receive_task)
            self._receive_task = None
        await self._client.disconnect()

    async def stop(self, frame: EndFrame) -> None:
        await super().stop(frame)
        await self._teardown()

    async def cancel(self, frame: CancelFrame) -> None:
        await super().cancel(frame)
        await self._teardown()

    async def cleanup(self) -> None:
        await super().cleanup()
        await self._teardown()
        await self._transport.cleanup()

    async def _receive_messages(self) -> None:
        try:
            async for message in self._client.receive():
                if not self._params.serializer:
                    continue
                frame = await self._params.serializer.deserialize(message)
                if not frame:
                    continue
                await self._push_deserialized(frame)
        except Exception as exc:  # noqa: BLE001 - a receive error ends the loop, never crashes
            _logger.error("aiohttp ws receive failed: %s (%s)", exc.__class__.__name__, exc)
        if not self._client.is_closing:
            await self._client.trigger_client_disconnected()

    async def _push_deserialized(self, frame: Frame) -> None:
        if isinstance(frame, InputAudioRawFrame):
            await self.push_audio_frame(frame)
        elif isinstance(frame, InputTransportMessageFrame):
            await self.broadcast_frame(InputTransportMessageFrame, message=frame.message)
        else:
            await self.push_frame(frame)


class AiohttpWebsocketOutputTransport(BaseOutputTransport):
    """Serializes outgoing frames and writes them to the WS, pacing audio like a device."""

    def __init__(self, transport, client: AiohttpWebsocketClient, params, **kwargs) -> None:
        super().__init__(params, **kwargs)
        self._transport = transport
        self._client = client
        self._params = params
        self._send_interval = 0
        self._next_send_time = 0
        self._initialized = False

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        if self._initialized:
            return
        self._initialized = True
        await self._client.setup(frame)
        if self._params.serializer:
            await self._params.serializer.setup(frame)
        self._send_interval = (self.audio_chunk_size / self.sample_rate) / 2
        await self.set_transport_ready(frame)

    async def stop(self, frame: EndFrame) -> None:
        await super().stop(frame)
        await self._write_frame(frame)
        await self._client.disconnect()

    async def cancel(self, frame: CancelFrame) -> None:
        await super().cancel(frame)
        await self._write_frame(frame)
        await self._client.disconnect()

    async def cleanup(self) -> None:
        await super().cleanup()
        await self._client.disconnect()
        await self._transport.cleanup()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InterruptionFrame):
            await self._write_frame(frame)
            self._next_send_time = 0

    async def send_message(self, frame) -> None:
        await self._write_frame(frame)

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        if self._client.is_closing or not self._client.is_connected:
            return False
        out = OutputAudioRawFrame(
            audio=frame.audio,
            sample_rate=self.sample_rate,
            num_channels=self._params.audio_out_channels,
        )
        if self._params.add_wav_header:
            out = self._with_wav_header(out)
        await self._write_frame(out)
        await self._write_audio_sleep()
        return True

    @staticmethod
    def _with_wav_header(frame: OutputAudioRawFrame) -> OutputAudioRawFrame:
        with io.BytesIO() as buffer:
            with wave.open(buffer, "wb") as wav:
                wav.setsampwidth(2)
                wav.setnchannels(frame.num_channels)
                wav.setframerate(frame.sample_rate)
                wav.writeframes(frame.audio)
            return OutputAudioRawFrame(
                buffer.getvalue(), sample_rate=frame.sample_rate, num_channels=frame.num_channels
            )

    async def _write_frame(self, frame: Frame) -> None:
        if self._client.is_closing or not self._client.is_connected or not self._params.serializer:
            return
        try:
            payload = await self._params.serializer.serialize(frame)
            if payload:
                await self._client.send(payload)
        except Exception as exc:  # noqa: BLE001 - a serialize/send error must not crash the pipeline
            _logger.error("aiohttp ws write failed: %s (%s)", exc.__class__.__name__, exc)

    async def _write_audio_sleep(self) -> None:
        current_time = time.monotonic()
        sleep_duration = max(0, self._next_send_time - current_time)
        await asyncio.sleep(sleep_duration)
        if sleep_duration == 0:
            self._next_send_time = time.monotonic() + self._send_interval
        else:
            self._next_send_time += self._send_interval


class AiohttpWebsocketTransport(BaseTransport):
    """Bidirectional pipecat transport over one aiohttp `WebSocketResponse` (no FastAPI)."""

    def __init__(
        self,
        websocket: web.WebSocketResponse,
        params: AiohttpWebsocketParams,
        input_name: str | None = None,
        output_name: str | None = None,
    ) -> None:
        super().__init__(input_name=input_name, output_name=output_name)
        self._params = params
        # BaseObject event seam (same as pipecat's WS transports): the client triggers
        # these so the handler can drain the session when the peer disconnects.
        self._client = AiohttpWebsocketClient(
            websocket,
            on_connected=self._trigger_connected,
            on_disconnected=self._trigger_disconnected,
        )
        self._input = AiohttpWebsocketInputTransport(
            self, self._client, params, name=self._input_name
        )
        self._output = AiohttpWebsocketOutputTransport(
            self, self._client, params, name=self._output_name
        )
        self._register_event_handler("on_client_connected")
        self._register_event_handler("on_client_disconnected")

    def input(self) -> AiohttpWebsocketInputTransport:
        return self._input

    def output(self) -> AiohttpWebsocketOutputTransport:
        return self._output

    async def _trigger_connected(self) -> None:
        await self._call_event_handler("on_client_connected", self._client)

    async def _trigger_disconnected(self) -> None:
        await self._call_event_handler("on_client_disconnected", self._client)


def build_aiohttp_ws_transport(
    websocket: web.WebSocketResponse,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    serializer: WebSocketAudioSerializer | None = None,
) -> AiohttpWebsocketTransport:
    """Construct the aiohttp WS audio transport for one accepted connection."""
    params = AiohttpWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_sample_rate=sample_rate,
        audio_out_sample_rate=sample_rate,
        add_wav_header=False,
        serializer=serializer or WebSocketAudioSerializer(),
    )
    return AiohttpWebsocketTransport(websocket, params)


class _ActiveSessions:
    """Single-loop concurrency counter (no lock needed: aiohttp handlers never preempt)."""

    def __init__(self) -> None:
        self.count = 0


def ws_async_max_sessions_config() -> int:
    """Resolve the async WS ceiling (ADR-0047 lifts the interim one-call cap).

    `VOICE_MAX_WS_SESSIONS` overrides `DEFAULT_MAX_WS_SESSIONS_ASYNC`; a non-numeric or
    non-positive value falls back to the default.
    """
    raw = os.environ.get(WS_MAX_SESSIONS_ENV_VAR)
    if raw is None:
        return DEFAULT_MAX_WS_SESSIONS_ASYNC
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_WS_SESSIONS_ASYNC
    return value if value > 0 else DEFAULT_MAX_WS_SESSIONS_ASYNC


def make_ws_handler(
    factory: SessionFactory,
    *,
    default_language: str | None = None,
    max_sessions: int = DEFAULT_MAX_WS_SESSIONS_ASYNC,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    allowed_origins: list[str] | None = None,
    serializer_factory: Callable[[], WebSocketAudioSerializer] = WebSocketAudioSerializer,
    telemetry_factory: Callable[[], TelemetryRecorder] = TelemetryRecorder,
    log: Callable[[TelemetryRecorder], None] = log_telemetry,
) -> Callable[[web.Request], Awaitable[web.WebSocketResponse]]:
    """Build the `GET /ws` handler: one session per connection, N concurrent (ADR-0047).

    Each accepted connection builds a `StreamingVoiceSession` via the shared `SessionFactory`
    and awaits it inline on the aiohttp loop. A connection above `max_sessions` is refused with
    WS close 1013 (try again later). Every outcome (accepted / closed / rejected) is stamped on
    the same telemetry names as the interim path for a cross-transport pilot chart.
    """
    active = _ActiveSessions()
    ceiling = max_sessions if max_sessions > 0 else DEFAULT_MAX_WS_SESSIONS_ASYNC

    async def handler(request: web.Request) -> web.WebSocketResponse:
        websocket = web.WebSocketResponse()
        await websocket.prepare(request)
        if allowed_origins and not is_origin_allowed(
            request.headers.get("Origin", ""), allowed_origins
        ):
            await websocket.close(code=1008)  # policy violation
            return websocket
        # Capacity check + slot reservation are synchronous (no await between them), so the
        # single-loop counter can't be oversubscribed by interleaved handlers.
        if active.count >= ceiling:
            await _reject(websocket, active, ceiling, default_language, telemetry_factory, log)
            return websocket
        await _serve_connection(
            websocket,
            request,
            factory=factory,
            active=active,
            max_sessions=ceiling,
            default_language=default_language,
            sample_rate=sample_rate,
            serializer_factory=serializer_factory,
            telemetry_factory=telemetry_factory,
            log=log,
        )
        return websocket

    return handler


async def _serve_connection(
    websocket: web.WebSocketResponse,
    request: web.Request,
    *,
    factory: SessionFactory,
    active: _ActiveSessions,
    max_sessions: int,
    default_language: str | None,
    sample_rate: int,
    serializer_factory: Callable[[], WebSocketAudioSerializer],
    telemetry_factory: Callable[[], TelemetryRecorder],
    log: Callable[[TelemetryRecorder], None],
) -> None:
    """Own one WS voice session end to end (build → run → teardown → telemetry dump)."""
    telemetry = telemetry_factory()
    serializer = serializer_factory()
    envelope = ChannelEnvelope.for_web_turn(language=default_language)
    transport = build_aiohttp_ws_transport(
        websocket, sample_rate=sample_rate, serializer=serializer
    )
    session, _ = factory.build_session(transport, envelope, telemetry)
    _wire_disconnect_drain(transport, session)
    cid = envelope.correlation_id
    active.count += 1
    telemetry.record(
        SESSION_STARTED_EVENT, correlation_id=cid, effective_language=envelope.language or "auto"
    )
    telemetry.record(
        CLIENT_CONNECTED_EVENT,
        correlation_id=cid,
        declared_language=(request.query.get("language") or ""),
        effective_language=envelope.language or "auto",
    )
    _emit_gauge(telemetry, cid, active.count, max_sessions, "accepted")
    try:
        await session.run()
    finally:
        await _safe_stop(session)
        active.count = max(0, active.count - 1)
        telemetry.record(CLIENT_DISCONNECTED_EVENT, correlation_id=cid)
        _emit_gauge(telemetry, cid, active.count, max_sessions, "closed")
        log(telemetry)


def _wire_disconnect_drain(transport: AiohttpWebsocketTransport, session: Any) -> None:
    """Drain the session when the peer disconnects so `session.run()` returns on its own.

    `drain()` queues an `EndFrame` (finalizes a trailing partial utterance, TASK-WEB-008)
    rather than cancelling, matching the graceful `closed`/`disconnected` path.
    """

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(_transport, _client) -> None:  # noqa: ANN001 - pipecat callback
        try:
            await session.drain()
        except Exception:  # noqa: BLE001 - drain is best-effort; run() still returns on cancel
            _logger.debug("drain on disconnect failed", exc_info=True)


async def _safe_stop(session: Any) -> None:
    try:
        await session.stop()
    except Exception:  # noqa: BLE001 - teardown must never raise out of the handler
        _logger.debug("session stop failed", exc_info=True)


async def _reject(
    websocket: web.WebSocketResponse,
    active: _ActiveSessions,
    max_sessions: int,
    default_language: str | None,
    telemetry_factory: Callable[[], TelemetryRecorder],
    log: Callable[[TelemetryRecorder], None],
) -> None:
    """Refuse an over-capacity connection with WS 1013 and record the refusal evidence."""
    telemetry = telemetry_factory()
    cid = ChannelEnvelope.for_web_turn(language=default_language).correlation_id
    telemetry.record(
        SESSION_REJECTED_EVENT,
        correlation_id=cid,
        reason=REASON_CAPACITY,
        active_sessions=active.count,
        max_sessions=max_sessions,
    )
    _emit_gauge(telemetry, cid, active.count, max_sessions, "rejected")
    log(telemetry)
    await websocket.close(code=WS_TRY_AGAIN_LATER)


def _emit_gauge(
    telemetry: TelemetryRecorder, cid: str, active_count: int, max_sessions: int, outcome: str
) -> None:
    telemetry.metric(
        ACTIVE_SESSIONS_METRIC,
        float(active_count),
        correlation_id=cid,
        outcome=outcome,
        max_sessions=max_sessions,
    )
