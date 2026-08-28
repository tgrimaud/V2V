"""Genesys Audio Connector wire framing serializer (TASK-WEB-041, ADR-0049).

The Genesys-facing counterpart of ``WebSocketAudioSerializer``. It keeps the exact same
AudioHook-shaped control channel (JSON control frames: ``open``/``opened``, ``close``/
``closed``, ``barge_in``, ``playback_started``/``playback_completed``, ``ping``/``pong``,
``language`` — the ADR-0043 vocabulary), so this subclass reuses all of it and only
overrides the **audio** path:

- inbound binary audio is the Genesys wire codec at 8 kHz (PCMU or L16) -> decoded and
  upsampled to the internal **PCM16 / 16 kHz** boundary before it enters the shared
  session core (ADR-0043: codec conversion lives inside the transport adapter, never in
  the core);
- outbound bot audio (PCM16 / 16 kHz) -> downsampled and encoded to the wire codec.

Per-leg transcode latency is emitted as ``genesys.transcode.in`` / ``genesys.transcode.out``
spans (the span names the TASK-WEB-025 spike used) when a telemetry recorder is injected,
stamped with the channel + codec + correlation id so a Genesys ``conversationId`` stitches
into one trace (TASK-WEB-043 reuses these on the live path). Barge-in ownership on the
Genesys path is TASK-WEB-042; this serializer already surfaces the native ``barge_in``
control frame as an ``InterruptionFrame`` so that ticket can drive it.
"""

from __future__ import annotations

from pipecat.frames.frames import AudioRawFrame, Frame, InputAudioRawFrame

from voice_common.telemetry import TelemetryRecorder, Timer

from . import genesys_codec
from .envelope import GENESYS_AUDIO_CONNECTOR_CHANNEL
from .websocket_framing import WebSocketAudioSerializer

TRANSCODE_IN_SPAN = "genesys.transcode.in"
TRANSCODE_OUT_SPAN = "genesys.transcode.out"
DEFAULT_INTERNAL_SAMPLE_RATE = 16000


class GenesysAudioConnectorSerializer(WebSocketAudioSerializer):
    """PCMU/L16 <-> PCM16/16 kHz codec + AudioHook control framing for the Genesys path."""

    class InputParams(WebSocketAudioSerializer.InputParams):
        """Framing parameters.

        Parameters:
            sample_rate: Internal PCM16 sample rate the session core runs at (16 kHz).
            wire_codec: Genesys wire codec ("L16" default, or "PCMU").
        """

        wire_codec: str = genesys_codec.DEFAULT_CODEC

    def __init__(
        self,
        params: "GenesysAudioConnectorSerializer.InputParams | None" = None,
        *,
        telemetry: TelemetryRecorder | None = None,
        correlation_id: str | None = None,
        **kwargs,
    ) -> None:
        params = params or GenesysAudioConnectorSerializer.InputParams()
        super().__init__(params, **kwargs)
        genesys_codec._require_supported(params.wire_codec)
        self._wire_codec = params.wire_codec
        self._telemetry = telemetry
        self._correlation_id = correlation_id

    @property
    def wire_codec(self) -> str:
        return self._wire_codec

    async def serialize(self, frame: Frame) -> str | bytes | None:
        """Bot audio -> wire codec bytes; everything else -> the AudioHook control channel."""
        if isinstance(frame, AudioRawFrame):
            return self._encode_outbound(frame)
        return await super().serialize(frame)

    def _encode_outbound(self, frame: AudioRawFrame) -> bytes | None:
        if not frame.audio:
            return None
        timer = Timer()
        wire = genesys_codec.from_internal_pcm16(bytes(frame.audio), self._wire_codec)
        self._span(TRANSCODE_OUT_SPAN, timer)
        return wire or None

    def _deserialize_audio(self, data: bytes) -> Frame | None:
        if not data:
            return None
        timer = Timer()
        pcm16_16k = genesys_codec.to_internal_pcm16(data, self._wire_codec)
        self._span(TRANSCODE_IN_SPAN, timer, frame_bytes=len(data))
        if not pcm16_16k:
            return None
        return InputAudioRawFrame(audio=pcm16_16k, num_channels=1, sample_rate=self._sample_rate)

    def _span(self, name: str, timer: Timer, **attributes) -> None:
        if self._telemetry is None:
            return
        self._telemetry.span(
            name,
            timer.elapsed_ms(),
            codec=self._wire_codec,
            channel=GENESYS_AUDIO_CONNECTOR_CHANNEL,
            correlation_id=self._correlation_id,
            **attributes,
        )
