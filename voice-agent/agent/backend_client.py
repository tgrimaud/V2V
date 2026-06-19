"""RAG backend client — calls the Java Spring Boot backend for conversation."""

import json
from collections.abc import AsyncGenerator

import httpx


class RAGBackendClient:
    """HTTP client to the Java backend's conversation API."""

    def __init__(self, base_url: str = "http://localhost:8081"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def ask(self, question: str, conversation_id: str = "pipecat") -> dict:
        """Send a question to the RAG backend and get an answer with citations."""
        response = await self._client.post(
            "/api/conversation/ask",
            json={"question": question, "conversationId": conversation_id},
        )
        response.raise_for_status()
        return response.json()

    async def ask_stream(
        self, question: str, conversation_id: str = "pipecat"
    ) -> AsyncGenerator[dict, None]:
        """Stream the RAG backend response via SSE. Yields dicts with 'event' and 'data' keys."""
        params = {"question": question, "conversation_id": conversation_id}
        async with self._client.stream(
            "GET",
            "/api/conversation/ask-stream",
            params=params,
            headers={"Accept": "text/event-stream"},
            timeout=60.0,
        ) as response:
            response.raise_for_status()
            event_name = ""
            data_buffer = ""

            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:"):
                    data_buffer = line[5:].strip()
                elif line == "" and data_buffer:
                    try:
                        parsed = json.loads(data_buffer)
                        yield {"event": event_name, "data": parsed}
                    except json.JSONDecodeError:
                        yield {"event": event_name, "data": {"text": data_buffer}}
                    event_name = ""
                    data_buffer = ""

    async def health(self) -> bool:
        """Check if the backend is reachable."""
        try:
            response = await self._client.get("/api/health")
            return response.status_code == 200
        except httpx.RequestError:
            return False

    async def close(self):
        await self._client.aclose()
