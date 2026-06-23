"""Tests for the streaming RAG sentence generator (strategy B)."""

import pytest

from agent.streaming_rag_processor import _FALLBACK_MESSAGE, iter_answer_sentences


class FakeBackend:
    """Fake RAGBackendClient yielding scripted SSE events."""

    def __init__(self, events):
        self._events = events

    async def ask_stream(self, question, conversation_id):
        for event in self._events:
            yield event


async def _collect(backend):
    return [s async for s in iter_answer_sentences(backend, "q", "conv-1")]


@pytest.mark.asyncio
async def test_emits_one_sentence_per_boundary():
    # GIVEN chunks that form two sentences
    backend = FakeBackend([
        {"event": "start", "data": {"agentName": "support"}},
        {"event": "chunk", "data": {"text": "Bonjour, comment allez-vous ? "}},
        {"event": "chunk", "data": {"text": "Je peux vous aider. "}},
        {"event": "done", "data": {"agentName": "support"}},
    ])
    # WHEN consumed
    sentences = await _collect(backend)
    # THEN each complete sentence is yielded separately
    assert sentences == ["Bonjour, comment allez-vous ?", "Je peux vous aider."]


@pytest.mark.asyncio
async def test_flushes_remainder_without_terminal_punctuation():
    # GIVEN a final chunk with no sentence-ending punctuation
    backend = FakeBackend([
        {"event": "chunk", "data": {"text": "Votre facture est disponible"}},
        {"event": "done", "data": {}},
    ])
    # WHEN consumed
    sentences = await _collect(backend)
    # THEN the trailing buffer is still emitted
    assert sentences == ["Votre facture est disponible"]


@pytest.mark.asyncio
async def test_error_event_yields_fallback_and_stops():
    # GIVEN an error event mid-stream
    backend = FakeBackend([
        {"event": "chunk", "data": {"text": "Un instant... "}},
        {"event": "error", "data": {"message": "boom"}},
        {"event": "chunk", "data": {"text": "ne devrait pas apparaitre. "}},
    ])
    # WHEN consumed
    sentences = await _collect(backend)
    # THEN the fallback is emitted and streaming stops
    assert sentences[-1] == _FALLBACK_MESSAGE
    assert "ne devrait pas apparaitre." not in sentences


@pytest.mark.asyncio
async def test_exception_yields_fallback():
    class ExplodingBackend:
        async def ask_stream(self, question, conversation_id):
            raise RuntimeError("network down")
            yield  # pragma: no cover

    # WHEN the backend raises
    sentences = await _collect(ExplodingBackend())
    # THEN the fallback message is yielded
    assert sentences == [_FALLBACK_MESSAGE]
