"""Voice runtime seam (Sprint 4 / TASK-WEB-005, ST-6).

The HTTP server talks to a `VoiceTurnProcessor` instead of the STT ingress / TTS
egress directly, so the two runtimes coexist and are selected at startup:

- `stdlib`: calls `WebVoiceIngress` / `WebVoiceEgress` directly (the pre-Sprint-4
  path, kept as the fallback / comparison runtime, ADR-0016).
- `pipecat`: runs each half through a Pipecat pipeline (ADR-0002 target runtime, in
  batch parity).

Both delegate to the same ingress/egress collaborators, so they produce identical
output for the same input; only the execution path differs. This is the composing
layer, so it may reference both halves.
"""

import threading
from typing import Any, Coroutine, Protocol

from conversation_backend import (
    AnswerOutcome,
    AnswerRequest,
    BackendAnswerPort,
    EmptyTranscriptError,
    StubBackendAdapter,
)
from stt_validation.models import SttOutcome
from tts_synthesis.models import TtsOutcome
from voice_pipeline.answer import answer_with_telemetry
from voice_pipeline.pipeline import BatchTurnResult, run_batch_turn, run_stt_turn, run_tts_turn

from .egress import VoiceResponse, WebVoiceEgress
from .ingress import WebVoiceIngress

STDLIB = "stdlib"
PIPECAT = "pipecat"
RUNTIME_NAMES = (STDLIB, PIPECAT)
# Sprint 4 ships pipecat as the default runtime (flipped in ST-9); stdlib stays
# selectable as the fallback / comparison path.
DEFAULT_RUNTIME = PIPECAT


class VoiceTurnProcessor(Protocol):
    """Runtime-agnostic seam the HTTP server drives for every voice turn."""

    def transcribe_turn(self, audio: bytes, envelope: Any, telemetry: Any = None, *, received_ms: float | None = None) -> Any: ...

    def synthesize_turn(self, text: str, envelope: Any, telemetry: Any = None) -> VoiceResponse: ...

    def record_egress(self, response: VoiceResponse, envelope: Any, telemetry: Any, *, sent_ms: float | None = None) -> None: ...

    def run_turn(self, audio: bytes, envelope: Any, telemetry: Any = None, *, received_ms: float | None = None) -> BatchTurnResult: ...


class StdlibTurnProcessor:
    """Runs the loop with the stdlib ingress/egress directly (no Pipecat)."""

    def __init__(
        self,
        ingress: WebVoiceIngress,
        egress: WebVoiceEgress,
        backend: BackendAnswerPort | None = None,
    ) -> None:
        self._ingress = ingress
        self._egress = egress
        self._backend = backend or StubBackendAdapter()

    def transcribe_turn(self, audio, envelope, telemetry=None, *, received_ms=None):
        return self._ingress.transcribe_turn(audio, envelope, telemetry, received_ms=received_ms)

    def synthesize_turn(self, text, envelope, telemetry=None) -> VoiceResponse:
        return self._egress.synthesize_turn(text, envelope, telemetry)

    def record_egress(self, response, envelope, telemetry, *, sent_ms=None) -> None:
        self._egress.record_egress(response, envelope, telemetry, sent_ms=sent_ms)

    def run_turn(self, audio, envelope, telemetry=None, *, received_ms=None) -> BatchTurnResult:
        result = self._ingress.transcribe_turn(audio, envelope, telemetry, received_ms=received_ms)
        if result.outcome is not SttOutcome.SUCCESS:
            return BatchTurnResult(transcript_result=result, tts_response=None, audio=b"")
        answer = self._answer(result.transcript, envelope, telemetry)
        if answer is None or not answer.text or answer.outcome is AnswerOutcome.UNAVAILABLE:
            return BatchTurnResult(transcript_result=result, tts_response=None, audio=b"", answer_result=answer)
        response = self._egress.synthesize_turn(answer.text, envelope, telemetry)
        audio = response.result.audio if response.result.outcome is TtsOutcome.SUCCESS else b""
        return BatchTurnResult(transcript_result=result, tts_response=response, audio=audio, answer_result=answer)

    def _answer(self, transcript, envelope, telemetry):
        try:
            request = AnswerRequest.from_envelope(transcript, envelope)
            return answer_with_telemetry(self._backend, request, telemetry)
        except EmptyTranscriptError:
            # STT SUCCESS carries a non-empty transcript; guard the boundary anyway so
            # a backend that signals "nothing to answer" never fabricates a turn.
            return None


class PipecatTurnProcessor:
    """Runs the loop through the Pipecat pipeline (batch parity).

    Each turn runs on a single persistent background asyncio loop (TASK-WEB-024) instead
    of `asyncio.run(...)` per HTTP turn, which created and tore down a fresh event loop on
    every request. The loop is created lazily on first use and pinned to one daemon thread;
    the threaded HTTP handler submits coroutines to it with `run_coroutine_threadsafe`
    (`BackgroundEventLoop.run`), exactly as the WebRTC path already does.
    """

    def __init__(
        self,
        ingress: WebVoiceIngress,
        egress: WebVoiceEgress,
        backend: BackendAnswerPort | None = None,
        loop: "BackgroundEventLoop | None" = None,
    ) -> None:
        self._ingress = ingress
        self._egress = egress
        self._backend = backend or StubBackendAdapter()
        self._loop = loop
        # Only close a loop this processor created; an injected one is caller-owned.
        self._owns_loop = loop is None
        self._loop_lock = threading.Lock()

    def _run(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Submit a coroutine to the shared background loop (created lazily, once)."""
        loop = self._loop
        if loop is None:
            with self._loop_lock:
                if self._loop is None:
                    from .async_loop import BackgroundEventLoop

                    self._loop = BackgroundEventLoop()
                    self._loop.start()
                loop = self._loop
        return loop.run(coro)

    def transcribe_turn(self, audio, envelope, telemetry=None, *, received_ms=None):
        return self._run(
            run_stt_turn(audio, envelope, ingress=self._ingress, telemetry=telemetry, received_ms=received_ms)
        )

    def synthesize_turn(self, text, envelope, telemetry=None) -> VoiceResponse:
        return self._run(run_tts_turn(text, envelope, egress=self._egress, telemetry=telemetry))

    def record_egress(self, response, envelope, telemetry, *, sent_ms=None) -> None:
        # The egress span is transport-owned; recording it needs no pipeline.
        self._egress.record_egress(response, envelope, telemetry, sent_ms=sent_ms)

    def run_turn(self, audio, envelope, telemetry=None, *, received_ms=None) -> BatchTurnResult:
        return self._run(
            run_batch_turn(
                audio,
                envelope,
                ingress=self._ingress,
                egress=self._egress,
                backend=self._backend,
                telemetry=telemetry,
                received_ms=received_ms,
            )
        )

    def close(self) -> None:
        """Stop the background loop on shutdown (only if this processor owns it)."""
        if self._owns_loop and self._loop is not None:
            self._loop.stop()
            self._loop = None


def build_turn_processor(
    runtime: str,
    ingress: WebVoiceIngress,
    egress: WebVoiceEgress,
    backend: BackendAnswerPort | None = None,
) -> VoiceTurnProcessor:
    if runtime == PIPECAT:
        return PipecatTurnProcessor(ingress, egress, backend)
    if runtime == STDLIB:
        return StdlibTurnProcessor(ingress, egress, backend)
    raise ValueError(f"unknown voice runtime: {runtime!r} (expected one of {RUNTIME_NAMES})")
