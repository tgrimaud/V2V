"""RAG backend client — calls the Java Spring Boot backend for conversation."""

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

    async def health(self) -> bool:
        """Check if the backend is reachable."""
        try:
            response = await self._client.get("/api/health")
            return response.status_code == 200
        except httpx.RequestError:
            return False

    async def close(self):
        await self._client.aclose()
