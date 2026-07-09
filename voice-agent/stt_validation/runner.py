from pathlib import Path
from uuid import uuid4

from .models import SttOutcome, TranscriptResult
from .providers import SttProvider
from .sanitization import sanitize_error
from .telemetry import TelemetryRecorder, Timer


class SttValidationRunner:
    def __init__(self, provider: SttProvider, telemetry: TelemetryRecorder) -> None:
        self._provider = provider
        self._telemetry = telemetry

    def validate(self, audio_path: Path, correlation_id: str | None = None) -> TranscriptResult:
        run_id = correlation_id or str(uuid4())
        total = Timer()
        self._telemetry.record(
            "stt.validation.started",
            correlation_id=run_id,
            provider=self._provider.name,
        )
        self._accept_audio(audio_path, run_id)
        self._telemetry.record(
            "stt.request.started",
            correlation_id=run_id,
            provider=self._provider.name,
        )
        stt = Timer()
        try:
            transcript = self._provider.transcribe(audio_path)
            return self._success(transcript, stt.elapsed_ms(), total.elapsed_ms(), run_id)
        except Exception as exc:  # noqa: BLE001 - failure must stay observable
            return self._failure(exc, stt.elapsed_ms(), total.elapsed_ms(), run_id)

    def _accept_audio(self, audio_path: Path, correlation_id: str) -> None:
        accept = Timer()
        audio_accepted = audio_path.exists()
        accept_ms = accept.elapsed_ms()
        self._telemetry.span(
            "stt.audio.accept",
            accept_ms,
            correlation_id=correlation_id,
            provider=self._provider.name,
            audio_accepted=audio_accepted,
        )
        self._telemetry.record(
            "stt.audio.accepted",
            correlation_id=correlation_id,
            provider=self._provider.name,
            audio_accepted=audio_accepted,
            audio_accept_ms=round(accept_ms, 3),
        )

    def _success(
        self,
        transcript: str,
        stt_request_ms: float,
        duration_ms: float,
        correlation_id: str,
    ) -> TranscriptResult:
        self._telemetry.span(
            "stt.request",
            stt_request_ms,
            correlation_id=correlation_id,
            provider=self._provider.name,
            outcome=SttOutcome.SUCCESS.value,
        )
        self._telemetry.record(
            "stt.transcript.final",
            correlation_id=correlation_id,
            provider=self._provider.name,
            stt_request_ms=round(stt_request_ms, 3),
        )
        result = TranscriptResult(
            transcript=transcript,
            provider=self._provider.name,
            outcome=SttOutcome.SUCCESS,
            duration_ms=duration_ms,
            stt_request_ms=stt_request_ms,
            correlation_id=correlation_id,
        )
        self._record_outcome(result)
        return result

    def _failure(
        self,
        exc: Exception,
        stt_request_ms: float,
        duration_ms: float,
        correlation_id: str,
    ) -> TranscriptResult:
        sanitized = sanitize_error(exc)
        self._telemetry.span(
            "stt.request",
            stt_request_ms,
            correlation_id=correlation_id,
            provider=self._provider.name,
            outcome=SttOutcome.FAILED.value,
        )
        self._telemetry.record(
            "stt.failure",
            correlation_id=correlation_id,
            provider=self._provider.name,
            error_code=sanitized.reason_code,
            error_reason=sanitized.reason,
            stt_request_ms=round(stt_request_ms, 3),
        )
        result = TranscriptResult(
            transcript="",
            provider=self._provider.name,
            outcome=SttOutcome.FAILED,
            duration_ms=duration_ms,
            stt_request_ms=stt_request_ms,
            correlation_id=correlation_id,
            error_code=sanitized.reason_code,
            error_reason=sanitized.reason,
        )
        self._record_outcome(result)
        return result

    def _record_outcome(self, result: TranscriptResult) -> None:
        attrs = self._outcome_attributes(result)
        self._telemetry.record(
            "stt.validation.completed",
            duration_ms=round(result.duration_ms, 3),
            stt_request_ms=round(result.stt_request_ms, 3),
            **attrs,
        )
        self._telemetry.metric("stt.request.duration_ms", result.stt_request_ms, **attrs)
        self._telemetry.metric("stt.validation.duration_ms", result.duration_ms, **attrs)
        if result.outcome is SttOutcome.SUCCESS:
            self._telemetry.log("info", "STT validation completed", **attrs)
        else:
            self._telemetry.log("warning", "STT validation failed", **attrs)

    def _outcome_attributes(self, result: TranscriptResult) -> dict[str, str]:
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
