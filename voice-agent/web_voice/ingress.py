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
from voice_common.telemetry import TelemetryRecorder, Timer

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
        providers_by_language: dict[str, SttProvider] | None = None,
    ) -> None:
        self._provider = provider
        self._audio_format = audio_format
        self._end_of_turn_detector = end_of_turn_detector or EndOfTurnDetector()
        # US-042: per-session STT providers keyed by language ("fr"/"en"). Empty on the
        # fixture/offline path, so the single default provider is always used there.
        self._providers_by_language = {
            key.lower(): value for key, value in (providers_by_language or {}).items()
        }

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def _provider_for(self, envelope: ChannelEnvelope) -> SttProvider:
        language = (getattr(envelope, "language", None) or "").lower()
        return self._providers_by_language.get(language, self._provider)

    def transcribe_turn(
        self,
        audio: bytes,
        envelope: ChannelEnvelope,
        telemetry: TelemetryRecorder | None = None,
        *,
        received_ms: float | None = None,
        detect_end_of_turn: bool = True,
    ) -> TranscriptResult:
        telemetry = telemetry or TelemetryRecorder()
        provider = self._provider_for(envelope)
        self._record_ingress(audio, envelope, telemetry, received_ms, provider)
        # The streaming path detects end-of-turn incrementally in the utterance
        # aggregator (TASK-STT-012) and already emitted the span, so the batch
        # detector is skipped there to avoid a duplicate voice.end_of_turn span.
        if detect_end_of_turn:
            self._detect_end_of_turn(audio, envelope, telemetry, provider)
        audio_path = _write_temp_audio(audio)
        try:
            runner = SttValidationRunner(provider, telemetry)
            return runner.validate(audio_path, envelope.correlation_id)
        finally:
            audio_path.unlink(missing_ok=True)

    def _detect_end_of_turn(
        self,
        audio: bytes,
        envelope: ChannelEnvelope,
        telemetry: TelemetryRecorder,
        provider: SttProvider,
    ) -> None:
        result = self._end_of_turn_detector.detect(audio)
        if not result.detected or result.slice_ms is None:
            # No usable speech -> no invented turn boundary; the slice stays
            # "not measured" for this turn rather than a fabricated latency.
            telemetry.record(
                "voice.end_of_turn.absent",
                correlation_id=envelope.correlation_id,
                channel=envelope.channel,
                provider=provider.name,
            )
            return
        attrs = self._end_of_turn_attrs(envelope, result, provider)
        telemetry.span(END_OF_TURN_SPAN, result.slice_ms, **attrs)
        telemetry.record("voice.end_of_turn.detected", **attrs)

    def _end_of_turn_attrs(
        self, envelope: ChannelEnvelope, result: EndOfTurnResult, provider: SttProvider
    ) -> dict[str, object]:
        return {
            "correlation_id": envelope.correlation_id,
            "channel": envelope.channel,
            "provider": provider.name,
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
        provider: SttProvider,
    ) -> None:
        # `received_ms` is the real time spent reading the audio off the wire,
        # measured by the transport (the server). When called without a transport
        # (unit tests / Behave), fall back to a locally measured window so the span
        # still carries the real received byte count.
        ingress_ms = received_ms if received_ms is not None else Timer().elapsed_ms()
        attrs = {
            **envelope.as_attributes(),
            "provider": provider.name,
            "audio_format": self._audio_format,
            "audio_bytes": len(audio),
        }
        telemetry.span("web.voice.ingress", ingress_ms, **attrs)
        telemetry.record("web.voice.ingress.received", audio_ingress_ms=round(ingress_ms, 3), **attrs)


def _write_temp_audio(audio: bytes) -> Path:
    with NamedTemporaryFile(prefix="web-voice-", suffix=".pcm", delete=False) as handle:
        handle.write(audio)
        return Path(handle.name)
