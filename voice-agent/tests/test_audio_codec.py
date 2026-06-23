"""Tests for the G.711 mu-law codec."""

from agent.audio_codec import (
    mulaw_decode_sample,
    mulaw_encode_sample,
    mulaw_to_pcm16,
    pcm16_to_mulaw,
)


# 0x7F is "negative zero": G.711 has two encodings of zero (0x7F and 0xFF);
# the encoder canonicalises zero to 0xFF, so 0x7F is the one non-round-tripping code.
_NEGATIVE_ZERO = 0x7F


def test_mulaw_roundtrip_is_identity_except_negative_zero():
    # GIVEN every mu-law byte apart from the negative-zero code
    # WHEN decoded then re-encoded
    # THEN the byte is recovered (mu-law encode/decode is otherwise a bijection)
    for mu in range(256):
        if mu == _NEGATIVE_ZERO:
            continue
        pcm = mulaw_decode_sample(mu)
        assert mulaw_encode_sample(pcm) == mu


def test_both_zero_encodings_decode_to_zero():
    # GIVEN the two G.711 zero codes
    # THEN both decode to zero and the encoder canonicalises to 0xFF
    assert mulaw_decode_sample(0x7F) == 0
    assert mulaw_decode_sample(0xFF) == 0
    assert mulaw_encode_sample(0) == 0xFF


def test_silence_byte_decodes_near_zero():
    # GIVEN the mu-law encoding of silence (0xFF)
    # WHEN decoded
    # THEN it is close to zero amplitude
    assert abs(mulaw_decode_sample(0xFF)) < 50


def test_decoded_samples_are_in_pcm16_range():
    # GIVEN all mu-law bytes
    # WHEN decoded
    # THEN samples fit signed 16-bit range
    for mu in range(256):
        sample = mulaw_decode_sample(mu)
        assert -32768 <= sample <= 32767


def test_byte_buffer_roundtrip_length_and_stability():
    # GIVEN a mu-law buffer excluding the negative-zero code
    mulaw = bytes(mu for mu in range(256) if mu != _NEGATIVE_ZERO)
    # WHEN decoded to PCM16 and re-encoded
    pcm = mulaw_to_pcm16(mulaw)
    # THEN PCM is twice the size (16-bit) and re-encoding recovers the buffer
    assert len(pcm) == len(mulaw) * 2
    assert pcm16_to_mulaw(pcm) == mulaw


def test_loud_positive_and_negative_samples_have_opposite_sign():
    # GIVEN a loud positive and a loud negative PCM sample
    loud_pos = mulaw_encode_sample(20000)
    loud_neg = mulaw_encode_sample(-20000)
    # WHEN decoded back
    # THEN signs are preserved
    assert mulaw_decode_sample(loud_pos) > 0
    assert mulaw_decode_sample(loud_neg) < 0
