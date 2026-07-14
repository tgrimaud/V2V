"""Disposable Pipecat spike (Sprint 4 / TASK-WEB-005, ST-1).

Goal: lock the exact pipecat-ai 1.5.0 API we depend on for a *batch*, in-memory
pipeline driven server-side (no transport, no streaming). It proves:

  - how to wrap logic as a `FrameProcessor` (async `process_frame`, call super,
    then `push_frame` downstream);
  - the frame types for the STT -> echo -> TTS batch loop
    (`InputAudioRawFrame` -> `TranscriptionFrame` -> `TextFrame`
    -> `TTSAudioRawFrame`);
  - how to inject input + `EndFrame` via `PipelineTask.queue_frames(...)` and run
    the pipeline to completion with `PipelineRunner.run(task)`;
  - how to collect the output audio via a capturing sink processor.

Runner-API note (locked here): pipecat 1.5.0 deprecates `PipelineTask`/`PipelineRunner`
in favour of `PipelineWorker`/`WorkerRunner`, but the new runner only consumes frames
queued *after* it is live (queuing up front leaves the `EndFrame` unconsumed and the
worker idle-hangs). For a *batch* driver we want "queue everything up front, run to
completion", which the `PipelineTask`/`PipelineRunner` pair supports directly. We pin
`pipecat-ai<2` and use that pair, silencing only its DeprecationWarning at the call
site. Revisit when Sprint 5 introduces a real (streaming) transport.

Run: `.venv/bin/python scripts/pipecat_spike.py`
This file is throwaway; the real services land in `voice_pipeline/` (ST-2..ST-4).
"""

import asyncio
import warnings

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InputAudioRawFrame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class FakeSttProcessor(FrameProcessor):
    """InputAudioRawFrame -> TranscriptionFrame (stands in for the STT runner)."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            text = f"transcript({len(frame.audio)} bytes)"
            await self.push_frame(
                TranscriptionFrame(text=text, user_id="spike", timestamp=""),
                direction,
            )
        else:
            await self.push_frame(frame, direction)


class EchoProcessor(FrameProcessor):
    """TranscriptionFrame -> TextFrame (the echo stub)."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            await self.push_frame(TextFrame(text=frame.text), direction)
        else:
            await self.push_frame(frame, direction)


class FakeTtsProcessor(FrameProcessor):
    """TextFrame -> TTSAudioRawFrame (stands in for the TTS runner)."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TextFrame):
            pcm = frame.text.encode("utf-8")  # fake "audio" keyed by text
            await self.push_frame(
                TTSAudioRawFrame(audio=pcm, sample_rate=16000, num_channels=1),
                direction,
            )
        else:
            await self.push_frame(frame, direction)


class CaptureSink(FrameProcessor):
    """Collects the emitted audio bytes so the caller can read the result."""

    def __init__(self) -> None:
        super().__init__()
        self.audio = bytearray()
        self.seen: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        self.seen.append(type(frame).__name__)
        if isinstance(frame, TTSAudioRawFrame):
            self.audio.extend(frame.audio)
        await self.push_frame(frame, direction)


async def run_batch_turn(audio: bytes) -> bytes:
    sink = CaptureSink()
    pipeline = Pipeline([FakeSttProcessor(), EchoProcessor(), FakeTtsProcessor(), sink])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="pipecat")
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
                InputAudioRawFrame(audio=audio, sample_rate=16000, num_channels=1),
                EndFrame(),
            ]
        )
        # handle_sigint=False is REQUIRED when driving off the main thread (HTTP server).
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)
    return bytes(sink.audio), sink.seen


def main() -> None:
    audio_in = b"\x00\x01" * 8  # 16 fake PCM bytes
    out, seen = asyncio.run(run_batch_turn(audio_in))
    print("frames seen at sink:", seen)
    print("output audio bytes:", out)
    expected = b"transcript(16 bytes)"
    print("PARITY OK" if out == expected else f"PARITY MISMATCH: {out!r} != {expected!r}")


if __name__ == "__main__":
    main()
