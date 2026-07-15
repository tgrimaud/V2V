"""Batch voice pipeline assembly + in-memory runner (Sprint 4 / TASK-WEB-005, ST-4;
backend answer step added in Sprint 5 / TASK-WEB-003-D).

Composes the Pipecat batch loop `STT -> backend answer -> TTS -> capture-sink` and
drives it to completion in memory (no transport, no streaming): the caller passes the
whole utterance audio, the runner queues it plus an `EndFrame` and collects the
synthesized audio at the sink. The answer step replaced the echo step so the loop
answers instead of speaking the transcript back.

This is the composing layer, so it may reference both halves via the injected
`ingress` / `egress` collaborators. It still avoids importing `web_voice` (whose
package init pulls both halves): the collaborators are duck-typed and injected by the
caller (the turn processor, ST-6).

Runner-API note: pipecat 1.5.0 deprecates `PipelineTask`/`PipelineRunner`, but the new
`WorkerRunner` only consumes frames queued after it is live, which does not fit a
"queue everything up front, run to completion" batch. We use the deprecated pair
(pinned `pipecat-ai<2`) and silence only its DeprecationWarning here. See
`docs/qa/pipecat-batch-contract.md`.
"""

import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pipecat.frames.frames import EndFrame, Frame, InputAudioRawFrame, TextFrame, TTSAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from conversation_backend import BackendAnswerPort, StubBackendAdapter

from .answer import AnswerProcessor
from .stt_service import SttFrameProcessor, SttIngress
from .tts_service import TtsEgress, TtsFrameProcessor

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_NUM_CHANNELS = 1


@dataclass(frozen=True)
class BatchTurnResult:
    """Outcome of one batch turn through the Pipecat pipeline.

    `transcript_result` is the STT `TranscriptResult` (or None if no audio was
    processed); `answer_result` is the backend `AnswerResult` (or None if the loop
    never reached the backend); `tts_response` is the egress `VoiceResponse`-like
    object (or None if synthesis never ran); `audio` is the synthesized PCM collected
    at the sink.
    """

    transcript_result: Any
    tts_response: Any
    audio: bytes
    answer_result: Any = None


class _AudioCaptureSink(FrameProcessor):
    """Terminal processor collecting the synthesized PCM emitted by the TTS stage."""

    def __init__(self) -> None:
        super().__init__()
        self.audio = bytearray()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            self.audio.extend(frame.audio)
        await self.push_frame(frame, direction)


async def _drive(processors: Sequence[FrameProcessor], input_frames: Sequence[Frame]) -> None:
    """Run a finite pipeline to completion: queue the input frames + EndFrame."""
    pipeline = Pipeline(list(processors))
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r".*deprecated.*", category=DeprecationWarning)
        # Imported inside the suppression window because importing the deprecated
        # classes and constructing/running them both emit DeprecationWarnings.
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask

        task = PipelineTask(
            pipeline,
            params=PipelineParams(),
            enable_rtvi=False,
            enable_turn_tracking=False,
            cancel_on_idle_timeout=False,
            check_dangling_tasks=False,
        )
        await task.queue_frames([*input_frames, EndFrame()])
        # handle_sigint=False is required when driving off the main thread (HTTP server).
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)


def _audio_frame(audio: bytes, sample_rate: int, num_channels: int) -> InputAudioRawFrame:
    return InputAudioRawFrame(audio=audio, sample_rate=sample_rate, num_channels=num_channels)


async def run_batch_turn(
    audio: bytes,
    envelope: Any,
    *,
    ingress: SttIngress,
    egress: TtsEgress,
    backend: BackendAnswerPort | None = None,
    telemetry: Any = None,
    received_ms: float | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    num_channels: int = DEFAULT_NUM_CHANNELS,
) -> BatchTurnResult:
    """Run one whole-utterance turn (audio -> STT -> backend answer -> TTS -> PCM) in memory.

    The backend defaults to the deterministic stub (offline dev/tests); the runtime
    injects the selected adapter (TASK-WEB-003-C adds `--backend`).
    """
    backend = backend or StubBackendAdapter()
    stt = SttFrameProcessor(ingress, envelope, telemetry, received_ms=received_ms)
    answer = AnswerProcessor(backend, envelope, telemetry)
    tts = TtsFrameProcessor(egress, envelope, telemetry)
    sink = _AudioCaptureSink()
    await _drive([stt, answer, tts, sink], [_audio_frame(audio, sample_rate, num_channels)])
    return BatchTurnResult(
        transcript_result=stt.result,
        tts_response=tts.response,
        audio=bytes(sink.audio),
        answer_result=answer.result,
    )


async def run_stt_turn(
    audio: bytes,
    envelope: Any,
    *,
    ingress: SttIngress,
    telemetry: Any = None,
    received_ms: float | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    num_channels: int = DEFAULT_NUM_CHANNELS,
) -> Any:
    """Run only the STT stage through Pipecat; return the TranscriptResult."""
    stt = SttFrameProcessor(ingress, envelope, telemetry, received_ms=received_ms)
    await _drive([stt], [_audio_frame(audio, sample_rate, num_channels)])
    return stt.result


async def run_tts_turn(
    text: str,
    envelope: Any,
    *,
    egress: TtsEgress,
    telemetry: Any = None,
) -> Any:
    """Run only the TTS stage through Pipecat; return the VoiceResponse-like object."""
    tts = TtsFrameProcessor(egress, envelope, telemetry)
    await _drive([tts], [TextFrame(text=text)])
    return tts.response
