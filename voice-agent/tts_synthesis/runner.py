from uuid import uuid4

from voice_common.sanitization import sanitize_error
from voice_common.telemetry import TelemetryRecorder, Timer

from .models import SynthesisResult, TtsOutcome
from .providers import DEFAULT_AUDIO_FORMAT, EmptyTextError, TtsProvider

# Span name for the TTS slice, consumed by pipeline_timing (TTS_FIRST_AUDIO). In
# batch (non-streaming) synthesis, first-audio latency equals the full request.
TTS_FIRST_AUDIO_SPAN = "voice.tts.first_audio"

# Stable code attached to an UNAVAILABLE outcome so QA/telemetry can filter
# "nothing to speak" apart from processing errors without parsing the message.
EMPTY_TEXT_CODE = "empty_text"

# outcome -> (log level, message). UNAVAILABLE is an expected, non-error result.
_OUTCOME_LOG: dict[TtsOutcome, tuple[str, str]] = {
    TtsOutcome.SUCCESS: ("info", "TTS synthesis completed"),
    TtsOutcome.UNAVAILABLE: ("info", "TTS had no text to speak"),
    TtsOutcome.FAILED: ("warning", "TTS synthesis failed"),
}


class TtsSynthesisRunner:
    """Voice-out mirror of SttValidationRunner: text -> audio with telemetry."""

    def __init__(self, provider: TtsProvider, telemetry: TelemetryRecorder) -> None:
        self._provider = provider
        self._telemetry = telemetry
        self._audio_format = getattr(provider, "audio_format", DEFAULT_AUDIO_FORMAT)

    def synthesize(self, text: str, correlation_id: str | None = None) -> SynthesisResult:
        run_id = correlation_id or str(uuid4())
        total = Timer()
        self._telemetry.record(
            "tts.synthesis.started",
            correlation_id=run_id,
            provider=self._provider.name,
        )
        self._telemetry.record(
            "tts.request.started",
            correlation_id=run_id,
            provider=self._provider.name,
        )
        request = Timer()
        try:
            audio = self._provider.synthesize(text)
            return self._success(audio, request.elapsed_ms(), total.elapsed_ms(), run_id)
        except EmptyTextError as exc:
            return self._unavailable(exc, request.elapsed_ms(), total.elapsed_ms(), run_id)
        except Exception as exc:  # noqa: BLE001 - failure must stay observable
            return self._failure(exc, request.elapsed_ms(), total.elapsed_ms(), run_id)

    def _success(
        self,
        audio: bytes,
        tts_request_ms: float,
        duration_ms: float,
        correlation_id: str,
    ) -> SynthesisResult:
        self._telemetry.span(
            TTS_FIRST_AUDIO_SPAN,
            tts_request_ms,
            correlation_id=correlation_id,
            provider=self._provider.name,
            outcome=TtsOutcome.SUCCESS.value,
        )
        self._telemetry.record(
            "tts.audio.final",
            correlation_id=correlation_id,
            provider=self._provider.name,
            audio_bytes=len(audio),
            tts_request_ms=round(tts_request_ms, 3),
        )
        result = SynthesisResult(
            audio=audio,
            provider=self._provider.name,
            outcome=TtsOutcome.SUCCESS,
            duration_ms=duration_ms,
            tts_request_ms=tts_request_ms,
            correlation_id=correlation_id,
            audio_format=self._audio_format,
        )
        self._record_outcome(result)
        return result

    def _failure(
        self,
        exc: Exception,
        tts_request_ms: float,
        duration_ms: float,
        correlation_id: str,
    ) -> SynthesisResult:
        sanitized = sanitize_error(exc, domain="tts")
        self._telemetry.span(
            TTS_FIRST_AUDIO_SPAN,
            tts_request_ms,
            correlation_id=correlation_id,
            provider=self._provider.name,
            outcome=TtsOutcome.FAILED.value,
        )
        self._telemetry.record(
            "tts.failure",
            correlation_id=correlation_id,
            provider=self._provider.name,
            error_code=sanitized.reason_code,
            error_reason=sanitized.reason,
            tts_request_ms=round(tts_request_ms, 3),
        )
        result = SynthesisResult(
            audio=b"",
            provider=self._provider.name,
            outcome=TtsOutcome.FAILED,
            duration_ms=duration_ms,
            tts_request_ms=tts_request_ms,
            correlation_id=correlation_id,
            audio_format=self._audio_format,
            error_code=sanitized.reason_code,
            error_reason=sanitized.reason,
        )
        self._record_outcome(result)
        return result

    def _unavailable(
        self,
        exc: EmptyTextError,
        tts_request_ms: float,
        duration_ms: float,
        correlation_id: str,
    ) -> SynthesisResult:
        reason = sanitize_error(exc, domain="tts").reason
        self._telemetry.span(
            TTS_FIRST_AUDIO_SPAN,
            tts_request_ms,
            correlation_id=correlation_id,
            provider=self._provider.name,
            outcome=TtsOutcome.UNAVAILABLE.value,
        )
        self._telemetry.record(
            "tts.unavailable",
            correlation_id=correlation_id,
            provider=self._provider.name,
            error_code=EMPTY_TEXT_CODE,
            error_reason=reason,
            tts_request_ms=round(tts_request_ms, 3),
        )
        result = SynthesisResult(
            audio=b"",
            provider=self._provider.name,
            outcome=TtsOutcome.UNAVAILABLE,
            duration_ms=duration_ms,
            tts_request_ms=tts_request_ms,
            correlation_id=correlation_id,
            audio_format=self._audio_format,
            error_code=EMPTY_TEXT_CODE,
            error_reason=reason,
        )
        self._record_outcome(result)
        return result

    def _record_outcome(self, result: SynthesisResult) -> None:
        attrs = self._outcome_attributes(result)
        self._telemetry.record(
            "tts.synthesis.completed",
            duration_ms=round(result.duration_ms, 3),
            tts_request_ms=round(result.tts_request_ms, 3),
            audio_bytes=len(result.audio),
            **attrs,
        )
        self._telemetry.metric("tts.request.duration_ms", result.tts_request_ms, **attrs)
        self._telemetry.metric("tts.synthesis.duration_ms", result.duration_ms, **attrs)
        level, message = _OUTCOME_LOG[result.outcome]
        self._telemetry.log(level, message, **attrs)

    def _outcome_attributes(self, result: SynthesisResult) -> dict[str, str]:
        attrs = {
            "correlation_id": result.correlation_id,
            "provider": result.provider,
            "outcome": result.outcome.value,
        }
        if result.error_code:
            attrs["error_code"] = result.error_code
        if result.error_reason:
            attrs["error_reason"] = result.error_reason
        return attrs
