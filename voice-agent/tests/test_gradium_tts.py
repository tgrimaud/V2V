"""Tests for gradium_tts module."""

import struct
import pytest

from agent.gradium_tts import pcm_to_wav, TTS_SAMPLE_RATE


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
