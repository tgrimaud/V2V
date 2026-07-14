"""Batch voice pipeline assembly + in-memory runner (Sprint 4 / TASK-WEB-005, ST-4).

Composes the Pipecat batch loop `STT -> echo -> TTS -> capture-sink` and drives it
to completion in memory (no transport, no streaming): the caller passes the whole
utterance audio, the runner queues it plus an `EndFrame` and collects the synthesized
audio at the sink.

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
from dataclasses import dataclass
from typing import Any

from pipecat.frames.frames import EndFrame, Frame, InputAudioRawFrame, TTSAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from .echo import EchoProcessor
from .stt_service import SttFrameProcessor, SttIngress
from .tts_service import TtsEgress, TtsFrameProcessor

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_NUM_CHANNELS = 1


@dataclass(frozen=True)
class BatchTurnResult:
    """Outcome of one batch turn through the Pipecat pipeline.

    `transcript_result` is the STT `TranscriptResult` (or None if no audio was
    processed); `tts_response` is the egress `VoiceResponse`-like object (or None if
    synthesis never ran); `audio` is the synthesized PCM collected at the sink.
    """

    transcript_result: Any
    tts_response: Any
    audio: bytes


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


async def run_batch_turn(
    audio: bytes,
    envelope: Any,
    *,
    ingress: SttIngress,
    egress: TtsEgress,
    telemetry: Any = None,
    received_ms: float | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    num_channels: int = DEFAULT_NUM_CHANNELS,
) -> BatchTurnResult:
    """Run one whole-utterance turn (audio -> STT -> echo -> TTS -> PCM) in memory."""
    stt = SttFrameProcessor(ingress, envelope, telemetry, received_ms=received_ms)
    echo = EchoProcessor()
    tts = TtsFrameProcessor(egress, envelope, telemetry)
    sink = _AudioCaptureSink()
    pipeline = Pipeline([stt, echo, tts, sink])

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
        await task.queue_frames(
            [
                InputAudioRawFrame(audio=audio, sample_rate=sample_rate, num_channels=num_channels),
                EndFrame(),
            ]
        )
        # handle_sigint=False is required when driving off the main thread (HTTP server).
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)

    return BatchTurnResult(
        transcript_result=stt.result,
        tts_response=tts.response,
        audio=bytes(sink.audio),
    )
