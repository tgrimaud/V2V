"""Pipecat TTS frame processor (Sprint 4 / TASK-WEB-005, ST-3).

Consumes a `TextFrame` and emits a `TTSAudioRawFrame`, delegating to the existing
web voice TTS egress so the `voice.tts.first_audio` telemetry, sanitization and
outcomes are identical to the stdlib path. This is the *batch* wrapper: it
synthesizes the whole text in one call (incremental/streaming TTS is Sprint 5).

The egress collaborator is injected (duck-typed `TtsEgress`) so this module never
imports `web_voice` (whose package init also pulls the STT half) nor
`stt_validation`, preserving the hard STT/TTS separation.

Note: several frame types subclass `TextFrame` (TranscriptionFrame,
InterimTranscriptionFrame = STT output), so we synthesize only *plain* `TextFrame`s
(the backend answer) via an exact-type allowlist and forward every subclass untouched.
The `web.voice.egress` span is intentionally NOT emitted here: it is measured by the
transport after the audio is actually sent (the turn processor calls the egress
`record_egress` with the real send window), preserving parity with the stdlib path.
"""

import asyncio
from typing import Any, Protocol

from pipecat.frames.frames import (
    Frame,
    TextFrame,
    TTSAudioRawFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from tts_synthesis.models import TtsOutcome


class TtsEgress(Protocol):
    """The subset of `WebVoiceEgress` this processor delegates to.

    `synthesize_turn` returns a `VoiceResponse`-like object exposing `.result`
    (a `SynthesisResult`) and `.wav` (bytes | None).
    """

    def synthesize_turn(self, text: str, envelope: Any, telemetry: Any = None) -> Any: ...


class TtsFrameProcessor(FrameProcessor):
    """`TextFrame` -> `TTSAudioRawFrame` via the TTS egress (batch)."""

    def __init__(self, egress: TtsEgress, envelope: Any, telemetry: Any = None) -> None:
        super().__init__()
        self._egress = egress
        self._envelope = envelope
        self._telemetry = telemetry
        # Last synthesis response (VoiceResponse-like), read by the turn processor to
        # send the WAV and emit the egress span on the real send window.
        self.response: Any = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        # Allowlist, not denylist: synthesize ONLY a *plain* answer TextFrame
        # (`type is TextFrame`). Every TextFrame *subclass* — TranscriptionFrame and
        # InterimTranscriptionFrame (final + live STT partials), and any future
        # subclass — is forwarded untouched, so the bot never speaks the customer's
        # own question back and a new subclass is safe by default.
        if type(frame) is TextFrame:
            await self._synthesize(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _synthesize(self, frame: TextFrame, direction: FrameDirection) -> None:
        # The egress does blocking work (provider I/O); keep it off the event loop.
        response = await asyncio.to_thread(
            self._egress.synthesize_turn,
            frame.text,
            self._envelope,
            self._telemetry,
        )
        self.response = response
        result = response.result
        if result.outcome is TtsOutcome.SUCCESS:
            await self.push_frame(
                TTSAudioRawFrame(
                    audio=result.audio,
                    sample_rate=_sample_rate_from_format(result.audio_format),
                    num_channels=1,
                ),
                direction,
            )
        # Non-success (FAILED / UNAVAILABLE): never invent audio, so nothing flows
        # downstream; the outcome is surfaced via `self.response`.


def _sample_rate_from_format(audio_format: str) -> int:
    # e.g. "pcm_16000" -> 16000; fall back to 16 kHz for an unexpected token.
    tail = audio_format.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 16000
