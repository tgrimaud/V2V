"""Streaming TTS frame processor for the WebRTC path (TASK-WEB-004).

Replaces the batch `TtsFrameProcessor` on the streaming path. Instead of
synthesizing the whole clip in one call and pushing a single `TTSAudioRawFrame`, it
streams the answer text to Gradium's WebSocket TTS (`GradiumStreamingTtsProvider`)
and pushes each `TTSAudioRawFrame` **as it arrives**, so the customer hears the
first words on the first synthesized chunk (~340 ms) instead of waiting for the full
clip (~1.6 s) — see `docs/qa/gradium-tts-contract.md`.

It owns the `voice.tts.first_audio` span on this path (same span name the batch
runner emits, so US-036 keeps measuring the `tts_first_audio` slice) with the span
duration = time-to-first-audio, and adds `tts.time_to_first_audio_ms` /
`tts.time_to_last_audio_ms` metrics. It lives in `web_voice` (the WebRTC composition
layer), keeping the transport-agnostic `voice_pipeline` TTS service free of the
streaming provider wiring.

Safety invariants (mirror of the batch runner): a non-success outcome never invents
audio — an empty answer is reported UNAVAILABLE and a provider error FAILED, and in
both cases nothing flows downstream. The API key never appears in a span, event or
log (only sanitized error codes do).
"""

from typing import Any

from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from tts_synthesis.models import TtsOutcome
from tts_synthesis.providers import EmptyTextError
from voice_common.sanitization import sanitize_error
from voice_common.telemetry import Timer

DEFAULT_PROVIDER_NAME = "gradium-tts-streaming"
TTS_FIRST_AUDIO_SPAN = "voice.tts.first_audio"
# Text was empty / nothing to speak — stable code so QA can filter it apart from a
# processing error without parsing the message (mirror of the batch runner).
EMPTY_TEXT_CODE = "empty_text"
DEFAULT_SAMPLE_RATE_HZ = 16000


class StreamingTtsProcessor(FrameProcessor):
    """`TextFrame` -> incremental `TTSAudioRawFrame`s via streaming TTS."""

    def __init__(
        self,
        provider: Any,
        envelope: Any,
        telemetry: Any = None,
        *,
        provider_name: str = DEFAULT_PROVIDER_NAME,
        sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._envelope = envelope
        self._telemetry = telemetry
        self._provider_name = provider_name
        self._sample_rate_hz = sample_rate_hz
        # Read by tests: number of chunks pushed on the last synthesis.
        self.chunk_count = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        # Synthesize only the plain answer TextFrame. BOTH TranscriptionFrame and
        # InterimTranscriptionFrame subclass TextFrame but are NOT plain answers:
        # they are upstream STT output (final + live partials from the streaming STT
        # processor). Synthesizing them would speak the customer's own question back.
        if isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
            await self.push_frame(frame, direction)
        elif isinstance(frame, TextFrame):
            await self._synthesize(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _synthesize(self, frame: TextFrame, direction: FrameDirection) -> None:
        text = frame.text
        timer = Timer()
        session = await self._provider.open()
        first_audio_ms: float | None = None
        chunk_count = 0
        try:
            await session.synthesize(text)
            async for chunk in session.stream():
                if first_audio_ms is None:
                    first_audio_ms = timer.elapsed_ms()
                chunk_count += 1
                await self._push_audio(chunk.pcm, direction)
        except EmptyTextError:
            await session.aclose()
            self._emit_unavailable(EMPTY_TEXT_CODE, timer.elapsed_ms())
            return
        except Exception as exc:  # noqa: BLE001 - failure stays observable (StreamingTtsError et al.)
            await session.aclose()
            self._emit_failure(exc, timer.elapsed_ms())
            return
        await session.aclose()
        self.chunk_count = chunk_count
        if chunk_count == 0:
            # Text was present but the provider streamed no audio — never invent any.
            self._emit_unavailable("no_audio", timer.elapsed_ms())
            return
        self._emit_success(first_audio_ms or 0.0, timer.elapsed_ms(), chunk_count)

    async def _push_audio(self, pcm: bytes, direction: FrameDirection) -> None:
        await self.push_frame(
            TTSAudioRawFrame(audio=pcm, sample_rate=self._sample_rate_hz, num_channels=1),
            direction,
        )

    def _emit_success(self, first_audio_ms: float, total_ms: float, chunk_count: int) -> None:
        if self._telemetry is None or self._envelope is None:
            return
        attrs = self._attrs(TtsOutcome.SUCCESS.value)
        self._telemetry.span(TTS_FIRST_AUDIO_SPAN, first_audio_ms, **attrs)
        self._telemetry.record(
            "tts.audio.final",
            time_to_first_audio_ms=round(first_audio_ms, 3),
            time_to_last_audio_ms=round(total_ms, 3),
            audio_chunks=chunk_count,
            **attrs,
        )
        self._telemetry.metric("tts.time_to_first_audio_ms", first_audio_ms, **attrs)
        self._telemetry.metric("tts.time_to_last_audio_ms", total_ms, **attrs)

    def _emit_unavailable(self, code: str, total_ms: float) -> None:
        if self._telemetry is None or self._envelope is None:
            return
        attrs = self._attrs(TtsOutcome.UNAVAILABLE.value)
        self._telemetry.span(TTS_FIRST_AUDIO_SPAN, total_ms, **attrs)
        self._telemetry.record("tts.unavailable", error_code=code, **attrs)

    def _emit_failure(self, exc: Exception, total_ms: float) -> None:
        if self._telemetry is None or self._envelope is None:
            return
        sanitized = sanitize_error(exc, domain="tts")
        attrs = self._attrs(TtsOutcome.FAILED.value)
        self._telemetry.span(TTS_FIRST_AUDIO_SPAN, total_ms, **attrs)
        self._telemetry.record(
            "tts.failure",
            error_code=sanitized.reason_code,
            error_reason=sanitized.reason,
            **attrs,
        )

    def _attrs(self, outcome: str) -> dict[str, Any]:
        return {
            "correlation_id": self._envelope.correlation_id,
            "provider": self._provider_name,
            "outcome": outcome,
        }
