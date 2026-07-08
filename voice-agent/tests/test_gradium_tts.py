"""Tests for gradium_tts module."""

import base64
import json
import struct
import pytest

from agent.gradium_tts import pcm_to_wav, synthesize_speech, TTS_SAMPLE_RATE


class FakeWebSocket:
    def __init__(self, received_messages):
        self._received_messages = list(received_messages)
        self.sent_messages = []

    async def send(self, message):
        self.sent_messages.append(json.loads(message))

    async def recv(self):
        return self._received_messages.pop(0)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._received_messages:
            raise StopAsyncIteration
        return self._received_messages.pop(0)


class FakeConnection:
    def __init__(self, websocket):
        self.websocket = websocket

    async def __aenter__(self):
        return self.websocket

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_pcm_to_wav_creates_valid_wav_header():
    """GIVEN raw PCM data
    WHEN pcm_to_wav is called
    THEN it returns data with a valid 44-byte WAV header."""
    # GIVEN
    pcm_data = b"\x00\x01" * 100  # 200 bytes of PCM

    # WHEN
    wav = pcm_to_wav(pcm_data, TTS_SAMPLE_RATE)

    # THEN
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert wav[12:16] == b"fmt "
    assert wav[36:40] == b"data"
    assert len(wav) == 44 + len(pcm_data)


def test_pcm_to_wav_encodes_correct_sample_rate():
    """GIVEN a specific sample rate
    WHEN pcm_to_wav is called
    THEN the WAV header contains the correct sample rate."""
    # GIVEN
    pcm_data = b"\x00" * 32000
    sample_rate = 16000

    # WHEN
    wav = pcm_to_wav(pcm_data, sample_rate)

    # THEN
    encoded_rate = struct.unpack_from('<I', wav, 24)[0]
    assert encoded_rate == 16000


def test_pcm_to_wav_preserves_pcm_data():
    """GIVEN specific PCM data
    WHEN pcm_to_wav is called
    THEN the PCM data is unchanged after the header."""
    # GIVEN
    pcm_data = bytes(range(256)) * 4

    # WHEN
    wav = pcm_to_wav(pcm_data)

    # THEN
    assert wav[44:] == pcm_data


@pytest.mark.asyncio
async def test_synthesize_speech_wraps_pcm_audio_as_wav(monkeypatch):
    """GIVEN Gradium returns PCM audio chunks
    WHEN synthesizing browser audio
    THEN the raw audio is wrapped in a WAV container."""
    # GIVEN
    pcm_data = b"\x01\x02\x03\x04"
    websocket = FakeWebSocket([
        json.dumps({"type": "ready"}),
        json.dumps({"type": "audio", "audio": base64.b64encode(pcm_data).decode()}),
        json.dumps({"type": "end_of_stream"}),
    ])
    monkeypatch.setattr(
        "agent.gradium_tts.websockets.connect",
        lambda *_args, **_kwargs: FakeConnection(websocket),
    )

    # WHEN
    audio = await synthesize_speech("Bonjour", "voice-1", "api-key")

    # THEN
    assert audio[:4] == b"RIFF"
    assert audio[44:] == pcm_data
    assert websocket.sent_messages == [
        {
            "type": "setup",
            "model_name": "default",
            "voice_id": "voice-1",
            "output_format": "pcm_16000",
        },
        {"type": "text", "text": "Bonjour"},
        {"type": "end_of_stream"},
    ]


@pytest.mark.asyncio
async def test_synthesize_speech_returns_raw_audio_for_ulaw(monkeypatch):
    """GIVEN Gradium returns mu-law audio
    WHEN synthesizing telephony audio
    THEN the raw bytes are returned unchanged."""
    # GIVEN
    raw_audio = b"\xff\xfe"
    websocket = FakeWebSocket([
        json.dumps({"type": "ready"}),
        json.dumps({"type": "audio", "audio": base64.b64encode(raw_audio).decode()}),
        json.dumps({"type": "end_of_stream"}),
    ])
    monkeypatch.setattr(
        "agent.gradium_tts.websockets.connect",
        lambda *_args, **_kwargs: FakeConnection(websocket),
    )

    # WHEN
    audio = await synthesize_speech("Bonjour", "voice-1", "api-key", "ulaw_8000")

    # THEN
    assert audio == raw_audio


@pytest.mark.asyncio
async def test_synthesize_speech_returns_none_when_setup_fails(monkeypatch):
    """GIVEN Gradium rejects setup
    WHEN synthesizing speech
    THEN no audio is returned."""
    # GIVEN
    websocket = FakeWebSocket([json.dumps({"type": "error", "message": "bad key"})])
    monkeypatch.setattr(
        "agent.gradium_tts.websockets.connect",
        lambda *_args, **_kwargs: FakeConnection(websocket),
    )

    # WHEN / THEN
    assert await synthesize_speech("Bonjour", "voice-1", "api-key") is None


@pytest.mark.asyncio
async def test_synthesize_speech_returns_none_on_connection_error(monkeypatch):
    """GIVEN the Gradium websocket cannot be opened
    WHEN synthesizing speech
    THEN the error is swallowed and no audio is returned."""
    # GIVEN
    def failing_connect(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("agent.gradium_tts.websockets.connect", failing_connect)

    # WHEN / THEN
    assert await synthesize_speech("Bonjour", "voice-1", "api-key") is None
