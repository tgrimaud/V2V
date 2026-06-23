"""G.711 mu-law (PCMU) codec for telephony audio.

Telephony transports (Twilio Media Streams, SIP/PSTN) carry 8 kHz mu-law audio.
The server-side turn detector and any local processing operate on linear PCM16,
so we need a dependency-free mu-law <-> PCM16 codec (Python 3.13 removed the
stdlib `audioop` module). The algorithm is the standard ITU-T G.711 mu-law.
"""

_MULAW_BIAS = 0x84
_MULAW_CLIP = 32635


def mulaw_decode_sample(mu_byte: int) -> int:
    """Decode one mu-law byte to a signed 16-bit PCM sample."""
    mu_byte = ~mu_byte & 0xFF
    sign = mu_byte & 0x80
    exponent = (mu_byte >> 4) & 0x07
    mantissa = mu_byte & 0x0F
    sample = (((mantissa << 3) + _MULAW_BIAS) << exponent) - _MULAW_BIAS
    return -sample if sign else sample


def mulaw_encode_sample(pcm_sample: int) -> int:
    """Encode one signed 16-bit PCM sample to a mu-law byte."""
    sign = 0x80 if pcm_sample < 0 else 0x00
    magnitude = -pcm_sample if pcm_sample < 0 else pcm_sample
    if magnitude > _MULAW_CLIP:
        magnitude = _MULAW_CLIP
    magnitude += _MULAW_BIAS

    exponent = 7
    mask = 0x4000
    while exponent > 0 and not (magnitude & mask):
        exponent -= 1
        mask >>= 1

    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


def mulaw_to_pcm16(mulaw_data: bytes) -> bytes:
    """Decode mu-law bytes to little-endian signed 16-bit PCM."""
    out = bytearray(len(mulaw_data) * 2)
    for i, mu in enumerate(mulaw_data):
        sample = mulaw_decode_sample(mu)
        out[2 * i] = sample & 0xFF
        out[2 * i + 1] = (sample >> 8) & 0xFF
    return bytes(out)


def pcm16_to_mulaw(pcm_data: bytes) -> bytes:
    """Encode little-endian signed 16-bit PCM to mu-law bytes."""
    usable = len(pcm_data) - (len(pcm_data) % 2)
    out = bytearray(usable // 2)
    for i in range(0, usable, 2):
        sample = int.from_bytes(pcm_data[i:i + 2], "little", signed=True)
        out[i // 2] = mulaw_encode_sample(sample)
    return bytes(out)
