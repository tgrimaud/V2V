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
from collections.abc import AsyncIterator

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from agent.backend_client import RAGBackendClient
from agent.sentence_splitter import find_sentence_boundary

_FALLBACK_MESSAGE = "Désolé, une erreur est survenue. Veuillez réessayer."


async def iter_answer_sentences(
    backend: RAGBackendClient, question: str, conversation_id: str
) -> AsyncIterator[str]:
    """Yield the RAG answer sentence-by-sentence as SSE tokens arrive.

    Pure (no Pipecat dependency) so it is unit-testable with a fake backend.
    Emits `_FALLBACK_MESSAGE` on an `error` event or exception. Also logs the
    `[LATENCY] step=llm_first_token` / `step=rag_total` lines for A/B comparison.
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

        if isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            if text:
                self._pending_parts.append(text)
                # Restart the debounce window: any in-flight wait OR answer is
                # cancelled so consecutive fragments coalesce into one turn.
                if self._flush_task is not None:
                    await self.cancel_task(self._flush_task)
                    self._flush_task = None
                self._flush_task = self.create_task(self._flush_after_delay())
        else:
            await self.push_frame(frame, direction)

    async def _flush_after_delay(self):
        try:
            await asyncio.sleep(self._aggregation_delay)

            question = " ".join(self._pending_parts).strip()
            self._pending_parts = []
            if not question:
                return

            logger.info(f"[RAG] Question: '{question}'")
            # Wrap the streamed sentences in LLM response boundaries so the TTS
            # aggregator flushes the final sentence at end-of-turn instead of
            # holding it until the next response (which jumbled text).
            # LLMTextFrame (vs plain TextFrame) makes the RTVI observer emit
            # botLlmStarted/botLlmText/botLlmStopped, giving the WebRTC client
            # (strategy B) clean per-answer turn boundaries to render one bubble
            # per response instead of merging consecutive answers.
            await self.push_frame(LLMFullResponseStartFrame())
            async for sentence in iter_answer_sentences(
                self._backend, question, self._conversation_id
            ):
                await self.push_frame(LLMTextFrame(text=sentence))
            await self.push_frame(LLMFullResponseEndFrame())
        finally:
            self._flush_task = None
