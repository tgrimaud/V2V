"""Channel-egress probe for the WebRTC streaming path (TASK-WEB-014).

The batch HTTP path measures channel egress in `WebVoiceEgress.record_egress` (the
WAV send window), so `web.voice.egress` is emitted only there. The streaming WebRTC
transport never calls it, leaving the CHANNEL_EGRESS slice a permanent gap on the
streaming path — the ADR-0018 / TASK-WEB-009 known gap. This probe closes that gap:
placed between the TTS processor and the transport output, it times the runtime
egress of the **first** synthesized audio frame of each spoken turn (the hand-off of
that frame to the WebRTC transport output) and emits the **same** `web.voice.egress`
span the batch path uses, so `PipelineTimingReport` measures CHANNEL_EGRESS on the
streaming path and the mouth-to-ear composite (`voice_to_first_audio`) folds it in.

Honest scope: this measures **runtime** egress (first frame -> transport output), not
the full browser-audible add-on (RTP encode/packetize + network + jitter buffer +
playout), which is not server-observable and stays a documented residual gap (see
`docs/observability/voice-journey-timing.md`). One span per spoken turn: the probe
arms at start and after each `BotStoppedSpeakingFrame`, and disarms on the first audio
frame it measures, so a multi-turn call yields one egress sample per turn.

No behaviour change to the audio itself: the probe always forwards the frame; when
telemetry/envelope are absent it is a pure pass-through (never invents a span).
"""

from typing import Any

from pipecat.frames.frames import BotStoppedSpeakingFrame, Frame, TTSAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from voice_common.telemetry import Timer

from .egress import CHANNEL_EGRESS_SPAN

DEFAULT_PROVIDER_NAME = "gradium-tts-streaming"
DEFAULT_TRANSPORT = "webrtc"
# Distinguishes this runtime-egress measurement from the batch WAV send window on the
# same span name, so a reviewer can tell the two egress semantics apart in the dump.
RUNTIME_EGRESS_MEASURE = "runtime_egress"


class ChannelEgressProbe(FrameProcessor):
    """Times the first audio frame's hand-off to the transport, per spoken turn."""

    def __init__(
        self,
        envelope: Any,
        telemetry: Any = None,
        *,
        provider_name: str = DEFAULT_PROVIDER_NAME,
        transport: str = DEFAULT_TRANSPORT,
    ) -> None:
        super().__init__()
        self._envelope = envelope
        self._telemetry = telemetry
        self._provider_name = provider_name
        self._transport = transport
        # Armed to measure the first audio frame of the first turn; re-armed after each
        # BotStoppedSpeakingFrame so every spoken turn contributes one egress sample.
        self._armed = True
        # Read by tests: number of egress spans emitted so far.
        self.egress_count = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if self._armed and isinstance(frame, TTSAudioRawFrame):
            await self._measure_egress(frame, direction)
            return
        if isinstance(frame, BotStoppedSpeakingFrame):
            # A spoken turn finished (this frame travels upstream from the output
            # transport); re-arm so the next turn's first audio frame is measured.
            self._armed = True
        await self.push_frame(frame, direction)

    async def _measure_egress(self, frame: TTSAudioRawFrame, direction: FrameDirection) -> None:
        self._armed = False
        timer = Timer()
        await self.push_frame(frame, direction)
        egress_ms = timer.elapsed_ms()
        self.egress_count += 1
        self._emit(egress_ms, len(frame.audio))

    def _emit(self, egress_ms: float, audio_bytes: int) -> None:
        if self._telemetry is None or self._envelope is None:
            return
        attrs = {
            "correlation_id": self._envelope.correlation_id,
            "provider": self._provider_name,
            "transport": self._transport,
            "measure": RUNTIME_EGRESS_MEASURE,
            "audio_bytes": audio_bytes,
        }
        self._telemetry.span(CHANNEL_EGRESS_SPAN, egress_ms, **attrs)
        self._telemetry.record(
            "web.voice.egress.sent", audio_egress_ms=round(egress_ms, 3), **attrs
        )
