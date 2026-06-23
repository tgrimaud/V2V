"""Streaming RAG processor for the Pipecat pipeline (strategy B).

Bridges Pipecat frames with the Java backend's *streaming* conversation API.
Unlike the batch `RAGProcessor` (single `ask()` then one `TextFrame`), this
consumes the SSE endpoint and pushes a `TextFrame` per sentence as tokens
arrive, so TTS starts speaking on the first sentence (low latency).

Sits between STT and TTS:  STT -> [TranscriptionFrame] -> here -> [TextFrame] -> TTS

Used by the unified Pipecat bot (`agent/bot.py`). Does not touch the custom
bridge (strategy A), which has its own SSE handling in `bridge_server.py`.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

from agent.backend_client import RAGBackendClient
from agent.sentence_splitter import find_sentence_boundary

_FALLBACK_MESSAGE = "Désolé, une erreur est survenue. Veuillez réessayer."


async def iter_answer_sentences(
    backend: RAGBackendClient,
    question: str,
    conversation_id: str,
    on_metadata: Callable[[str], Awaitable[None]] | None = None,
) -> AsyncIterator[str]:
    """Yield the RAG answer sentence-by-sentence as SSE tokens arrive.

    Pure (no Pipecat dependency) so it is unit-testable with a fake backend.
    Emits `_FALLBACK_MESSAGE` on an `error` event or exception. Also logs the
    `[LATENCY] step=llm_first_token` / `step=rag_total` lines for A/B comparison.

    ``on_metadata`` is awaited with the resolved agent name (from the SSE
    ``start`` event) so the caller can forward it to the client — strategy A
    shows which routed agent (Facturation / Support / Commercial) is answering.
    """
    start = time.perf_counter()
    first_chunk = True
    buffer = ""
    agent_name = None

    try:
        async for sse in backend.ask_stream(question, conversation_id):
            event = sse.get("event")
            data = sse.get("data", {})

            if event == "start":
                agent_name = data.get("agentName")
                if on_metadata is not None and agent_name:
                    await on_metadata(agent_name)
            elif event == "chunk":
                if first_chunk:
                    ms = (time.perf_counter() - start) * 1000
                    print(f"[LATENCY] step=llm_first_token ms={ms:.0f}", flush=True)
                    first_chunk = False
                buffer += data.get("text", "")
                sentence, remainder = find_sentence_boundary(buffer)
                while sentence:
                    yield sentence
                    buffer = remainder
                    sentence, remainder = find_sentence_boundary(buffer)
            elif event == "error":
                yield _FALLBACK_MESSAGE
                return

        if buffer.strip():
            yield buffer.strip()

        total = (time.perf_counter() - start) * 1000
        print(f"[LATENCY] step=rag_total ms={total:.0f} agent={agent_name}", flush=True)
    except Exception as exc:
        logger.error(f"RAG streaming error: {exc}")
        yield _FALLBACK_MESSAGE


class StreamingRAGProcessor(FrameProcessor):
    """Streams per-sentence answers from the RAG backend into the TTS stage.

    A single user turn often arrives as *several* final ``TranscriptionFrame``s
    when the speaker pauses mid-thought (e.g. "j'ai un souci sur ma facture" …
    "je ne comprends pas pourquoi je paye"). Triggering one RAG turn per frame
    makes the bot answer each fragment and "talk over itself".

    To avoid that, transcription fragments are buffered and the RAG call is only
    fired after ``aggregation_delay`` seconds without a new fragment. Each new
    fragment cancels the pending flush (and any answer already streaming), which
    also gives us natural barge-in: if the user speaks again, the current turn is
    dropped and the buffer is re-evaluated.
    """

    def __init__(
        self,
        backend: RAGBackendClient,
        conversation_id: str = "pipecat",
        aggregation_delay: float = 1.5,
    ):
        super().__init__()
        self._backend = backend
        self._conversation_id = conversation_id
        self._aggregation_delay = aggregation_delay
        self._pending_parts: list[str] = []
        self._flush_task = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InterruptionFrame):
            # Barge-in: the user started talking over the bot. The framework
            # already stops TTS playback; we must also drop any answer still
            # streaming (and the buffered question) so the bot doesn't keep
            # speaking the rest of the response after being cut off.
            await self._cancel_flush(clear_buffer=True)
            await self.push_frame(frame, direction)
        elif isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            if text:
                self._pending_parts.append(text)
                # Restart the debounce window: any in-flight wait OR answer is
                # cancelled so consecutive fragments coalesce into one turn.
                await self._cancel_flush(clear_buffer=False)
                self._flush_task = self.create_task(self._flush_after_delay())
        else:
            await self.push_frame(frame, direction)

    async def _cancel_flush(self, *, clear_buffer: bool):
        if self._flush_task is not None:
            await self.cancel_task(self._flush_task)
            self._flush_task = None
        if clear_buffer:
            self._pending_parts = []

    async def _flush_after_delay(self):
        try:
            await asyncio.sleep(self._aggregation_delay)

            question = " ".join(self._pending_parts).strip()
            self._pending_parts = []
            if not question:
                return

            # Log size only — the question text is user PII.
            logger.info(f"[RAG] Question received ({len(question)} chars)")
            await self._stream_answer(question)
        finally:
            self._flush_task = None

    async def _stream_answer(self, question: str):
        async def _emit_agent_name(agent_name: str):
            # Forward the routed agent to the WebRTC client so it can label
            # the bubble (same as strategy A's per-message agent badge).
            await self.push_frame(
                RTVIServerMessageFrame(
                    data={"type": "agent_name", "agent_name": agent_name}
                )
            )

        # Wrap the streamed sentences in LLM response boundaries so the TTS
        # aggregator flushes the final sentence at end-of-turn. LLMTextFrame
        # (vs plain TextFrame) makes the RTVI observer emit botLlmStarted/
        # botLlmText/botLlmStopped, giving the WebRTC client clean per-answer
        # turn boundaries. The End frame is emitted in finally so a mid-stream
        # cancel (barge-in) never leaves an orphan Start frame.
        response_open = False
        try:
            await self.push_frame(LLMFullResponseStartFrame())
            response_open = True
            async for sentence in iter_answer_sentences(
                self._backend,
                question,
                self._conversation_id,
                on_metadata=_emit_agent_name,
            ):
                await self.push_frame(LLMTextFrame(text=sentence))
        finally:
            if response_open:
                await self.push_frame(LLMFullResponseEndFrame())
