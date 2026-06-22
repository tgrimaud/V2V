"""Tests for the streaming STT abstraction."""

import pytest
from unittest.mock import AsyncMock, patch

from agent.gradium_stt import SttResult
from agent.stt_streaming import BatchSttSession, StreamingSttSession, create_stt_session


def test_factory_returns_streaming_session():
    # GIVEN the active engine factory
    session = create_stt_session("fr", "fake-key")
    # THEN it satisfies the StreamingSttSession protocol
    assert isinstance(session, StreamingSttSession)


@pytest.mark.asyncio
async def test_batch_session_accumulates_and_transcribes_once():
    # GIVEN a batch session fed in several chunks
    session = BatchSttSession("fr", "fake-key")
    session.feed(b"\x01\x02")
    session.feed(b"\x03\x04")

    with patch("agent.stt_streaming.transcribe_audio", new=AsyncMock(
            return_value=SttResult(text="bonjour"))) as mock_stt:
        # WHEN finalized
        result = await session.finalize()

    # THEN the accumulated buffer is transcribed once and text is returned
    mock_stt.assert_awaited_once_with(b"\x01\x02\x03\x04", "fr", "fake-key")
    assert result.text == "bonjour"


@pytest.mark.asyncio
async def test_batch_session_empty_returns_no_text_without_calling_stt():
    # GIVEN an empty session
    session = BatchSttSession("fr", "fake-key")

    with patch("agent.stt_streaming.transcribe_audio", new=AsyncMock()) as mock_stt:
        # WHEN finalized
        result = await session.finalize()

    # THEN no STT call is made and result has no text
    mock_stt.assert_not_awaited()
    assert result.text is None
