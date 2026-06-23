"""Tests for the streaming RAG sentence generator (strategy B)."""

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

from agent.streaming_rag_processor import (
    _FALLBACK_MESSAGE,
    StreamingRAGProcessor,
    iter_answer_sentences,
)


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
async def test_on_metadata_receives_agent_name_from_start_event():
    # GIVEN a stream whose start event names the routed agent
    backend = FakeBackend([
        {"event": "start", "data": {"agentName": "Agent Facturation"}},
        {"event": "chunk", "data": {"text": "Votre facture. "}},
        {"event": "done", "data": {}},
    ])
    seen: list[str] = []

    async def capture(name: str):
        seen.append(name)

    # WHEN consumed with an on_metadata callback
    sentences = [
        s
        async for s in iter_answer_sentences(
            backend, "q", "conv-1", on_metadata=capture
        )
    ]

    # THEN the agent name is forwarded once and answers still stream
    assert seen == ["Agent Facturation"]
    assert sentences == ["Votre facture."]


@pytest.mark.asyncio
async def test_on_metadata_not_called_when_agent_name_absent():
    # GIVEN a stream with no agentName in the start event
    backend = FakeBackend([
        {"event": "start", "data": {}},
        {"event": "chunk", "data": {"text": "Bonjour. "}},
        {"event": "done", "data": {}},
    ])
    seen: list[str] = []

    async def capture(name: str):
        seen.append(name)

    # WHEN consumed
    _ = [
        s
        async for s in iter_answer_sentences(
            backend, "q", "conv-1", on_metadata=capture
        )
    ]

    # THEN the callback is never invoked
    assert seen == []


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


async def _capture_stream_answer(backend) -> list:
    """Run _stream_answer in isolation and capture the pushed frame types."""
    processor = StreamingRAGProcessor(backend, "conv-1")
    pushed: list = []

    async def fake_push(frame, *args, **kwargs):
        pushed.append(frame)

    processor.push_frame = fake_push  # type: ignore[assignment]
    await processor._stream_answer("question")
    return pushed


@pytest.mark.asyncio
async def test_stream_answer_wraps_sentences_in_llm_response_boundaries():
    # GIVEN a backend that streams one sentence with a routed agent
    backend = FakeBackend([
        {"event": "start", "data": {"agentName": "Agent Facturation"}},
        {"event": "chunk", "data": {"text": "Votre facture est prête. "}},
        {"event": "done", "data": {}},
    ])
    # WHEN the processor streams the answer
    pushed = await _capture_stream_answer(backend)
    types = [type(f).__name__ for f in pushed]

    # THEN the text frames are bracketed by start/end response frames
    assert types[0] == LLMFullResponseStartFrame.__name__
    assert types[-1] == LLMFullResponseEndFrame.__name__
    text_frames = [f for f in pushed if isinstance(f, LLMTextFrame)]
    assert [f.text for f in text_frames] == ["Votre facture est prête."]


@pytest.mark.asyncio
async def test_stream_answer_emits_agent_name_server_message():
    # GIVEN a stream whose start event names the routed agent
    backend = FakeBackend([
        {"event": "start", "data": {"agentName": "Agent Facturation"}},
        {"event": "chunk", "data": {"text": "Bonjour. "}},
        {"event": "done", "data": {}},
    ])
    # WHEN the processor streams the answer
    pushed = await _capture_stream_answer(backend)

    # THEN an RTVI server message carries the agent name to the client
    server_messages = [f for f in pushed if isinstance(f, RTVIServerMessageFrame)]
    assert len(server_messages) == 1
    assert server_messages[0].data == {
        "type": "agent_name",
        "agent_name": "Agent Facturation",
    }


@pytest.mark.asyncio
async def test_stream_answer_without_agent_name_emits_no_server_message():
    # GIVEN a stream with no agent name
    backend = FakeBackend([
        {"event": "start", "data": {}},
        {"event": "chunk", "data": {"text": "Bonjour. "}},
        {"event": "done", "data": {}},
    ])
    # WHEN the processor streams the answer
    pushed = await _capture_stream_answer(backend)

    # THEN no RTVI server message is pushed
    assert not [f for f in pushed if isinstance(f, RTVIServerMessageFrame)]


@pytest.mark.asyncio
async def test_stream_answer_always_closes_response_even_when_empty():
    # GIVEN a stream that yields no sentences at all
    backend = FakeBackend([
        {"event": "start", "data": {}},
        {"event": "done", "data": {}},
    ])
    # WHEN the processor streams the answer
    pushed = await _capture_stream_answer(backend)
    types = [type(f).__name__ for f in pushed]

    # THEN the response is still opened and closed (no orphan start frame)
    assert types == [
        LLMFullResponseStartFrame.__name__,
        LLMFullResponseEndFrame.__name__,
    ]
