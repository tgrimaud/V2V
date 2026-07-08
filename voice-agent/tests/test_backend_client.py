"""Tests for the Java backend HTTP client."""

import json

import httpx
import pytest

from agent.backend_client import RAGBackendClient


def _client_with_handler(handler):
    client = RAGBackendClient("http://backend:8081/")
    client._client = httpx.AsyncClient(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
    )
    return client


@pytest.mark.asyncio
async def test_ask_sends_snake_case_conversation_id_and_returns_json():
    """GIVEN a backend client
    WHEN asking a question
    THEN it posts the expected JSON payload and returns the backend response."""
    # GIVEN
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"answer": "Bonjour"})

    client = _client_with_handler(handler)

    # WHEN
    result = await client.ask("Ma facture ?", "conv-42")

    # THEN
    assert seen == {
        "url": "http://backend:8081/api/conversation/ask",
        "body": {"question": "Ma facture ?", "conversation_id": "conv-42"},
    }
    assert result == {"answer": "Bonjour"}


@pytest.mark.asyncio
async def test_seed_greeting_posts_assistant_message_to_backend():
    """GIVEN a backend client
    WHEN seeding the greeting
    THEN it sends the greeting with the configured conversation id."""
    # GIVEN
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(204)

    client = _client_with_handler(handler)

    # WHEN
    await client.seed_greeting("Bonjour !", "conv-1")

    # THEN
    assert seen["body"] == {"message": "Bonjour !", "conversation_id": "conv-1"}


@pytest.mark.asyncio
async def test_ask_stream_parses_json_and_plain_text_sse_events():
    """GIVEN an SSE response with JSON and plain text data
    WHEN consuming the stream
    THEN parsed events preserve event names and payloads."""
    # GIVEN
    sse = (
        "event: start\n"
        'data: {"agentName": "Support"}\n\n'
        "event: chunk\n"
        "data: Bonjour\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["conversation_id"] == "conv-1"
        return httpx.Response(200, content=sse)

    client = _client_with_handler(handler)

    # WHEN
    events = [event async for event in client.ask_stream("Salut", "conv-1")]

    # THEN
    assert events == [
        {"event": "start", "data": {"agentName": "Support"}},
        {"event": "chunk", "data": {"text": "Bonjour"}},
    ]


@pytest.mark.asyncio
async def test_health_returns_false_when_backend_request_fails():
    """GIVEN the backend cannot be reached
    WHEN checking health
    THEN the client reports an unhealthy backend."""
    # GIVEN
    request = httpx.Request("GET", "http://backend:8081/api/health")

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = _client_with_handler(handler)

    # WHEN / THEN
    assert await client.health() is False


@pytest.mark.asyncio
async def test_health_returns_true_for_http_200():
    """GIVEN the backend health endpoint answers 200
    WHEN checking health
    THEN the client reports a healthy backend."""
    # GIVEN
    client = _client_with_handler(lambda _request: httpx.Response(200))

    # WHEN / THEN
    assert await client.health() is True
