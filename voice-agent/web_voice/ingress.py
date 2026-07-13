"""Web voice ingress: browser audio -> channel envelope -> STT transcript.

The ingress adds a real channel-ingress span (audio bytes actually received over
the wire) instead of the scaffold `path.exists()` analog flagged by RF-002, then
delegates transcription to the existing SttValidationRunner so the STT slice
telemetry, sanitization and outcome stay identical to the fixture path.
"""

from pathlib import Path
from tempfile import NamedTemporaryFile

from stt_validation.models import TranscriptResult
from stt_validation.providers import SttProvider
from stt_validation.runner import SttValidationRunner
from stt_validation.telemetry import TelemetryRecorder, Timer

from .end_of_turn import END_OF_TURN_SPAN, EndOfTurnDetector, EndOfTurnResult
from .envelope import ChannelEnvelope

DEFAULT_AUDIO_FORMAT = "pcm_16000"


class WebVoiceIngress:
    def __init__(
        self,
        provider: SttProvider,
        *,
        audio_format: str = DEFAULT_AUDIO_FORMAT,
        end_of_turn_detector: EndOfTurnDetector | None = None,
    ) -> None:
        self._provider = provider
        self._audio_format = audio_format
        self._end_of_turn_detector = end_of_turn_detector or EndOfTurnDetector()

    def transcribe_turn(
        self,
        audio: bytes,
        envelope: ChannelEnvelope,
        telemetry: TelemetryRecorder | None = None,
        *,
        received_ms: float | None = None,
    ) -> TranscriptResult:
        telemetry = telemetry or TelemetryRecorder()
        self._record_ingress(audio, envelope, telemetry, received_ms)
        self._detect_end_of_turn(audio, envelope, telemetry)
        audio_path = _write_temp_audio(audio)
        try:
            runner = SttValidationRunner(self._provider, telemetry)
            return runner.validate(audio_path, envelope.correlation_id)
        finally:
            audio_path.unlink(missing_ok=True)

    def _detect_end_of_turn(
        self,
        audio: bytes,
        envelope: ChannelEnvelope,
        telemetry: TelemetryRecorder,
    ) -> None:
        result = self._end_of_turn_detector.detect(audio)
        if not result.detected or result.slice_ms is None:
            # No usable speech -> no invented turn boundary; the slice stays
            # "not measured" for this turn rather than a fabricated latency.
            telemetry.record(
                "voice.end_of_turn.absent",
                correlation_id=envelope.correlation_id,
                channel=envelope.channel,
                provider=self._provider.name,
            )
            return
        attrs = self._end_of_turn_attrs(envelope, result)
        telemetry.span(END_OF_TURN_SPAN, result.slice_ms, **attrs)
        telemetry.record("voice.end_of_turn.detected", **attrs)

    def _end_of_turn_attrs(self, envelope: ChannelEnvelope, result: EndOfTurnResult) -> dict[str, object]:
        return {
            "correlation_id": envelope.correlation_id,
            "channel": envelope.channel,
            "provider": self._provider.name,
            "end_of_turn_signal": result.signal,
            "trailing_silence_ms": round(result.trailing_silence_ms, 3),
            "speech_end_ms": round(result.speech_end_ms, 3) if result.speech_end_ms is not None else None,
        }

    def _record_ingress(
        self,
        audio: bytes,
        envelope: ChannelEnvelope,
        telemetry: TelemetryRecorder,
        received_ms: float | None,
    ) -> None:
        # `received_ms` is the real time spent reading the audio off the wire,
        # measured by the transport (the server). When called without a transport
        # (unit tests / Behave), fall back to a locally measured window so the span
        # still carries the real received byte count.
        ingress_ms = received_ms if received_ms is not None else Timer().elapsed_ms()
        attrs = {
            **envelope.as_attributes(),
            "provider": self._provider.name,
            "audio_format": self._audio_format,
            "audio_bytes": len(audio),
        }
        telemetry.span("web.voice.ingress", ingress_ms, **attrs)
        telemetry.record("web.voice.ingress.received", audio_ingress_ms=round(ingress_ms, 3), **attrs)


def _write_temp_audio(audio: bytes) -> Path:
    with NamedTemporaryFile(prefix="web-voice-", suffix=".pcm", delete=False) as handle:
        handle.write(audio)
        return Path(handle.name)
