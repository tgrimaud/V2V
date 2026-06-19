"""RAG processor — bridges Pipecat frames with the Java backend's conversation API."""

from pipecat.frames.frames import Frame, TextFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from agent.backend_client import RAGBackendClient


class RAGProcessor(FrameProcessor):
    """Receives transcription frames, queries the RAG backend, emits text frames.

    This processor sits between STT and TTS in the pipeline:
      STT → [TranscriptionFrame] → RAGProcessor → [TextFrame] → TTS
    """

    def __init__(self, backend: RAGBackendClient, conversation_id: str = "pipecat"):
        super().__init__()
        self._backend = backend
        self._conversation_id = conversation_id

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            if not text:
                return

            try:
                result = await self._backend.ask(text, self._conversation_id)
                answer = result.get("answer", "Désolé, je n'ai pas compris.")
                await self.push_frame(TextFrame(text=answer))
            except Exception as e:
                error_msg = "Désolé, une erreur est survenue. Veuillez réessayer."
                await self.push_frame(TextFrame(text=error_msg))

        else:
            await self.push_frame(frame, direction)
