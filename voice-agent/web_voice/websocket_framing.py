"""Wire framing for the interim browser WebSocket audio transport (TASK-WEB-026).

ADR-0043: one long-lived ``wss`` connection carries **JSON control frames** (text)
plus **binary PCM16 / 16 kHz audio frames**. This serializer is the frame-demux seam
of pipecat's ``WebsocketServerTransport`` (no FastAPI); it is deliberately modelled on
the *shape* of the Genesys AudioHook protocol (``pipecat.serializers.genesys``) — JSON
control + binary audio — so the Sprint 13 Genesys Audio Connector reuses this layer
instead of rebuilding it. We adopt the shape, not the exact AudioHook schema (YAGNI:
ADR-0040 is a gated spike).

Demux rule (deterministic, the AC of TASK-WEB-026):
- a **binary** WebSocket message is audio  -> ``InputAudioRawFrame`` (PCM16, mono, 16 kHz)
- a **text** WebSocket message is control   -> parsed as JSON ``{"type": ...}``

The internal control vocabulary mirrors Genesys semantics (ADR-0043 point 4) so the
control-signal seam maps 1:1 later: ``open``/``opened``, ``close``/``closed``,
``barge_in``, ``playback_started``/``playback_completed``, ``call_end``, ``language``,
``ping``/``pong``.
"""

import json
from typing import Any

from pipecat.frames.frames import (
    AudioRawFrame,
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    OutputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
    StartFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer


class ControlType:
    """Internal control-frame vocabulary (mirrors Genesys AudioHook semantics)."""

    OPEN = "open"
    OPENED = "opened"
    CLOSE = "close"
    CLOSED = "closed"
    CALL_END = "call_end"
    BARGE_IN = "barge_in"
    LANGUAGE = "language"
    PLAYBACK_STARTED = "playback_started"
    PLAYBACK_COMPLETED = "playback_completed"
    PING = "ping"
    PONG = "pong"


class WebSocketAudioSerializer(FrameSerializer):
    """JSON-control + binary-PCM16/16 kHz framing for the browser WebSocket path.

    Straight-through PCM16 (no codec transcoding on the browser path — the
    client already captures 16 kHz mono PCM16 via an AudioWorklet, TASK-WEB-028).
    Genesys PCMU/L16-8 kHz transcoding stays inside its own adapter (Sprint 13);
    no sample-rate assumption leaks into the shared session core (ADR-0043).
    """

    class InputParams(FrameSerializer.InputParams):
        """Framing parameters.

        Parameters:
            sample_rate: Wire PCM16 sample rate for the browser path (16 kHz).
        """

        sample_rate: int = 16000

    def __init__(self, params: "WebSocketAudioSerializer.InputParams | None" = None, **kwargs):
        params = params or WebSocketAudioSerializer.InputParams()
        super().__init__(params, **kwargs)
        self._params: WebSocketAudioSerializer.InputParams = params
        self._sample_rate = params.sample_rate
        self._selected_language: str | None = None
        self._is_open = False

    @property
    def selected_language(self) -> str | None:
        """Language selected by the client at ``open``/``language`` (US-042)."""
        return self._selected_language

    @property
    def is_open(self) -> bool:
        """Whether the client sent ``open`` and has not yet ``close``d."""
        return self._is_open

    async def setup(self, frame: StartFrame):
        """Adopt the pipeline input sample rate when the pipeline starts."""
        self._sample_rate = self._params.sample_rate or frame.audio_in_sample_rate

    # -- outbound: pipeline frame -> wire ------------------------------------

    async def serialize(self, frame: Frame) -> str | bytes | None:
        """Bot audio -> binary PCM16; lifecycle/interruption -> JSON control text."""
        if isinstance(frame, AudioRawFrame):
            return bytes(frame.audio) if frame.audio else None
        if isinstance(frame, InterruptionFrame):
            return json.dumps({"type": ControlType.BARGE_IN})
        if isinstance(frame, (EndFrame, CancelFrame)):
            return json.dumps({"type": ControlType.CALL_END})
        if isinstance(frame, (OutputTransportMessageFrame, OutputTransportMessageUrgentFrame)):
            return self._serialize_transport_message(frame)
        return None

    def _serialize_transport_message(self, frame: Frame) -> str | None:
        if self.should_ignore_frame(frame):
            return None
        message = getattr(frame, "message", None)
        return json.dumps(message) if isinstance(message, dict) else None

    # -- inbound: wire -> pipeline frame -------------------------------------

    async def deserialize(self, data: str | bytes) -> Frame | None:
        """Binary -> audio frame; text -> JSON control (deterministic demux)."""
        if isinstance(data, (bytes, bytearray)):
            return self._deserialize_audio(bytes(data))
        return self._handle_control(self._parse_json(data))

    def _deserialize_audio(self, data: bytes) -> Frame | None:
        if not data:
            return None
        return InputAudioRawFrame(audio=data, num_channels=1, sample_rate=self._sample_rate)

    @staticmethod
    def _parse_json(data: str) -> dict[str, Any] | None:
        try:
            message = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return None
        return message if isinstance(message, dict) else None

    def _handle_control(self, message: dict[str, Any] | None) -> Frame | None:
        if message is None:
            return None
        handler = self._CONTROL_HANDLERS.get(message.get("type", ""))
        return handler(self, message) if handler else None

    def _on_open(self, message: dict[str, Any]) -> Frame:
        self._is_open = True
        self._selected_language = message.get("language") or self._selected_language
        return OutputTransportMessageUrgentFrame(message={"type": ControlType.OPENED})

    def _on_close(self, message: dict[str, Any]) -> Frame:
        self._is_open = False
        return OutputTransportMessageUrgentFrame(message={"type": ControlType.CLOSED})

    def _on_language(self, message: dict[str, Any]) -> None:
        self._selected_language = message.get("language") or self._selected_language
        return None

    def _on_barge_in(self, message: dict[str, Any]) -> Frame:
        return InterruptionFrame()

    def _on_ping(self, message: dict[str, Any]) -> Frame:
        return OutputTransportMessageUrgentFrame(message={"type": ControlType.PONG})

    _CONTROL_HANDLERS = {
        ControlType.OPEN: _on_open,
        ControlType.CLOSE: _on_close,
        ControlType.CALL_END: _on_close,
        ControlType.LANGUAGE: _on_language,
        ControlType.BARGE_IN: _on_barge_in,
        ControlType.PING: _on_ping,
    }
