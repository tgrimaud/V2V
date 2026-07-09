from pathlib import Path
from uuid import uuid4

from .models import SttOutcome, TranscriptResult
from .providers import SttProvider
from .telemetry import TelemetryRecorder, Timer


class SttValidationRunner:
    def __init__(self, provider: SttProvider, telemetry: TelemetryRecorder) -> None:
        self._provider = provider
        self._telemetry = telemetry

    def validate(self, audio_path: Path, correlation_id: str | None = None) -> TranscriptResult:
        run_id = correlation_id or str(uuid4())
        timer = Timer()
        self._telemetry.record("stt.validation.started", correlation_id=run_id, provider=self._provider.name)
        try:
            transcript = self._provider.transcribe(audio_path)
            return self._success(transcript, timer.elapsed_ms(), run_id)
        except Exception as exc:
            return self._failure(str(exc), timer.elapsed_ms(), run_id)

    def _success(self, transcript: str, duration_ms: float, correlation_id: str) -> TranscriptResult:
        self._record_outcome(SttOutcome.SUCCESS, duration_ms, correlation_id)
        return TranscriptResult(transcript, self._provider.name, SttOutcome.SUCCESS, duration_ms, correlation_id)

    def _failure(self, reason: str, duration_ms: float, correlation_id: str) -> TranscriptResult:
        self._record_outcome(SttOutcome.FAILED, duration_ms, correlation_id, reason)
        return TranscriptResult("", self._provider.name, SttOutcome.FAILED, duration_ms, correlation_id, reason)

    def _record_outcome(
        self,
        outcome: SttOutcome,
        duration_ms: float,
        correlation_id: str,
        error_reason: str | None = None,
    ) -> None:
        attrs = self._outcome_attributes(outcome, correlation_id, error_reason)
        self._telemetry.record(
            "stt.validation.completed",
            duration_ms=duration_ms,
            **attrs,
        )
        self._telemetry.metric("stt.validation.duration_ms", duration_ms, **attrs)
        self._telemetry.log("info", "STT validation completed", **attrs)

    def _outcome_attributes(
        self,
        outcome: SttOutcome,
        correlation_id: str,
        error_reason: str | None,
    ) -> dict[str, str]:
        attrs = {"correlation_id": correlation_id, "provider": self._provider.name, "outcome": outcome.value}
        if error_reason:
            attrs["error_reason"] = error_reason
        return attrs
