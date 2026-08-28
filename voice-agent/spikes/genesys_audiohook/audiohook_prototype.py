"""THROWAWAY AudioHook session prototype for the Genesys spike (TASK-WEB-025).

Models one bidirectional Audio Connector session **in-process** (no real socket, no
live org) so the synthetic harness can time the transport + transcode legs. It reuses
the real ADR-0043 AudioHook-shaped control vocabulary (``web_voice.websocket_framing.
ControlType``: open/opened/close/closed/barge_in/...) to stay faithful to the target
framing, and the real ``voice_common`` telemetry so a Genesys ``conversationId`` maps
to one OpenTelemetry trace. In the real target (TASK-WEB-041) this becomes a transport
adapter mounted on the ADR-0047 single async HTTP+WebSocket server via the ADR-0043
session factory — here it is a throwaway driver, isolated under ``spikes/`` and never
imported by the production runtime.

The bot audio comes from an **injected** ``runtime`` callable (``bytes -> bytes``, PCM16
in / PCM16 out). The spike injects a synthetic stub, so **no backend business code is
touched** (ADR-0001 boundary invariant holds).
"""

from __future__ import annotations

import json
from typing import Callable

from voice_common.telemetry import TelemetryRecorder, Timer
from web_voice.websocket_framing import ControlType

from .transcode import from_internal_pcm16, to_internal_pcm16

Runtime = Callable[[bytes], bytes]


class AudioHookSessionPrototype:
    """Throwaway one-stream Audio Connector session (synthetic audio only)."""

    THROWAWAY = True

    def __init__(self, telemetry: TelemetryRecorder, *, codec: str, conversation_id: str) -> None:
        self._telemetry = telemetry
        self._codec = codec
        self._conversation_id = conversation_id
        self._open = False

    def run_turn(self, wire_frames: list[bytes], runtime: Runtime) -> bytes:
        """One synthetic round trip: caller wire frames -> bot wire frames."""
        self._handshake_open()
        pcm16_16k = self._ingest(wire_frames)
        bot_pcm16 = runtime(pcm16_16k)
        out_frames = self._emit(bot_pcm16)
        self._handshake_close()
        return out_frames

    def _handshake_open(self) -> None:
        json.dumps({"type": ControlType.OPEN, "conversationId": self._conversation_id})
        self._open = True

    def _handshake_close(self) -> None:
        json.dumps({"type": ControlType.CLOSED})
        self._open = False

    def _ingest(self, wire_frames: list[bytes]) -> bytes:
        demuxed = self._demux_inbound(wire_frames)
        return self._transcode_inbound(demuxed)

    def _demux_inbound(self, wire_frames: list[bytes]) -> list[bytes]:
        timer = Timer()
        audio = [frame for frame in wire_frames if isinstance(frame, (bytes, bytearray))]
        self._span("genesys.wss.inbound", timer, frames=len(wire_frames))
        return audio

    def _transcode_inbound(self, wire_frames: list[bytes]) -> bytes:
        timer = Timer()
        pcm = b"".join(to_internal_pcm16(frame, self._codec) for frame in wire_frames)
        self._span("genesys.transcode.in", timer, codec=self._codec, frames=len(wire_frames))
        return pcm

    def _emit(self, bot_pcm16_16k: bytes) -> bytes:
        wire = self._transcode_outbound(bot_pcm16_16k)
        return self._frame_outbound(wire)

    def _transcode_outbound(self, bot_pcm16_16k: bytes) -> bytes:
        timer = Timer()
        wire = from_internal_pcm16(bot_pcm16_16k, self._codec)
        self._span("genesys.transcode.out", timer, codec=self._codec)
        return wire

    def _frame_outbound(self, wire: bytes) -> bytes:
        timer = Timer()
        payload = bytes(wire)
        self._span("genesys.wss.outbound", timer, bytes=len(payload))
        return payload

    def _span(self, name: str, timer: Timer, **attributes) -> None:
        self._telemetry.span(name, timer.elapsed_ms(), correlation_id=self._conversation_id, **attributes)
