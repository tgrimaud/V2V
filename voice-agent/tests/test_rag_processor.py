"""Tests for the batch RAG Pipecat processor."""

import pytest
from pipecat.frames.frames import TextFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection

from agent.rag_processor import RAGProcessor


class FakeBackend:
    def __init__(self, result=None, error=None):
        self.result = result or {}
        self.error = error
        self.calls = []

    async def ask(self, question, conversation_id):
        self.calls.append((question, conversation_id))
        if self.error is not None:
            raise self.error
        return self.result


def make_transcription(text):
    try:
        return TranscriptionFrame(text=text, user_id="user-1", timestamp="ts")
    except TypeError:
        return TranscriptionFrame(text=text)


def capture_pushed_frames(processor):
    pushed = []

    async def capture(frame, direction=None):
        pushed.append((frame, direction))

    processor.push_frame = capture
    return pushed


@pytest.mark.asyncio
async def test_process_frame_pushes_backend_answer_for_transcription():
    """GIVEN a transcription frame and a healthy backend
    WHEN the processor handles the frame
    THEN it pushes the backend answer as a TextFrame."""
    # GIVEN
    backend = FakeBackend({"answer": "Voici la réponse."})
    processor = RAGProcessor(backend, "conv-1")
    pushed = capture_pushed_frames(processor)

    # WHEN
    await processor.process_frame(
        make_transcription("  Ma question ?  "),
        FrameDirection.DOWNSTREAM,
    )

    # THEN
    assert backend.calls == [("Ma question ?", "conv-1")]
    assert len(pushed) == 1
    assert isinstance(pushed[0][0], TextFrame)
    assert pushed[0][0].text == "Voici la réponse."


@pytest.mark.asyncio
async def test_process_frame_ignores_empty_transcription():
    """GIVEN an empty transcription frame
    WHEN the processor handles the frame
    THEN no backend call or answer frame is emitted."""
    # GIVEN
    backend = FakeBackend({"answer": "ignored"})
    processor = RAGProcessor(backend)
    pushed = capture_pushed_frames(processor)

    # WHEN
    await processor.process_frame(make_transcription("   "), FrameDirection.DOWNSTREAM)

    # THEN
    assert backend.calls == []
    assert pushed == []


@pytest.mark.asyncio
async def test_process_frame_pushes_fallback_when_backend_fails():
    """GIVEN the backend raises an error
    WHEN the processor handles a transcription
    THEN a user-friendly fallback answer is pushed."""
    # GIVEN
    backend = FakeBackend(error=RuntimeError("backend down"))
    processor = RAGProcessor(backend)
    pushed = capture_pushed_frames(processor)

    # WHEN
    await processor.process_frame(make_transcription("Aidez-moi"), FrameDirection.DOWNSTREAM)

    # THEN
    assert len(pushed) == 1
    assert pushed[0][0].text == "Désolé, une erreur est survenue. Veuillez réessayer."


@pytest.mark.asyncio
async def test_process_frame_passes_non_transcription_frames_through():
    """GIVEN a non-transcription frame
    WHEN the processor handles it
    THEN the frame is forwarded unchanged."""
    # GIVEN
    backend = FakeBackend()
    processor = RAGProcessor(backend)
    pushed = capture_pushed_frames(processor)
    frame = TextFrame(text="already synthesized")

    # WHEN
    await processor.process_frame(frame, FrameDirection.DOWNSTREAM)

    # THEN
    assert pushed == [(frame, FrameDirection.DOWNSTREAM)]
