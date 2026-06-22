"""Tests for gradium_stt module."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent.gradium_stt import transcribe_audio


@pytest.mark.asyncio
async def test_transcribe_audio_returns_joined_words():
    """GIVEN audio data and a successful Gradium response
    WHEN transcribe_audio is called
    THEN it returns an SttResult whose text is the words joined with spaces."""
    # GIVEN
    ndjson_response = "\n".join([
        json.dumps({"type": "text", "text": "Bonjour", "start_s": 0.5}),
        json.dumps({"type": "end_text", "stop_s": 0.8}),
        json.dumps({"type": "text", "text": "le", "start_s": 0.9}),
        json.dumps({"type": "end_text", "stop_s": 1.0}),
        json.dumps({"type": "text", "text": "monde.", "start_s": 1.1}),
        json.dumps({"type": "end_text", "stop_s": 1.4}),
    ])

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ndjson_response

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("agent.gradium_stt.httpx.AsyncClient", return_value=mock_client):
        # WHEN
        result = await transcribe_audio(b"\x00" * 3200, "fr", "fake-key")

    # THEN
    assert result.text == "Bonjour le monde."
    assert result.error_code is None


@pytest.mark.asyncio
async def test_transcribe_audio_returns_error_on_http_error():
    """GIVEN a failed HTTP response from Gradium
    WHEN transcribe_audio is called
    THEN it returns an SttResult with an error code and no text."""
    # GIVEN
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("agent.gradium_stt.httpx.AsyncClient", return_value=mock_client):
        # WHEN
        result = await transcribe_audio(b"\x00" * 3200, "fr", "fake-key")

    # THEN
    assert result.text is None
    assert result.error_code == "STT_ERROR"


@pytest.mark.asyncio
async def test_transcribe_audio_returns_empty_on_silence():
    """GIVEN an empty response from Gradium (silence)
    WHEN transcribe_audio is called
    THEN it returns an SttResult with no text and no error."""
    # GIVEN
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = json.dumps({"type": "end_of_stream"})

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("agent.gradium_stt.httpx.AsyncClient", return_value=mock_client):
        # WHEN
        result = await transcribe_audio(b"\x00" * 3200, "fr", "fake-key")

    # THEN
    assert result.text is None
    assert result.error_code is None
