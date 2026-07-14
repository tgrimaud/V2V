"""Echo frame processor (Sprint 4 / TASK-WEB-005, ST-4).

Reproduces the current echo stub: turn the STT `TranscriptionFrame` into a plain
`TextFrame` carrying the same text, so the TTS stage speaks back the transcript.
This is the batch, no-backend loop (a real LLM/RAG answer is TASK-WEB-003). The
processor is domain-neutral: it imports neither `stt_validation` nor `tts_synthesis`.
"""

from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class EchoProcessor(FrameProcessor):
    """`TranscriptionFrame` -> plain `TextFrame` (echo of the transcript)."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            await self.push_frame(TextFrame(text=frame.text), direction)
        else:
            await self.push_frame(frame, direction)
