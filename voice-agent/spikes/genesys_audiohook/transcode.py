"""Codec transcode budget for the Genesys Audio Connector spike (TASK-WEB-025).

Genesys Audio Connector offers two audio codecs on the wire:
- **PCMU** (G.711 µ-law, 8 kHz) — forces a transcode to the Gradium PCM16/16 kHz
  internal boundary (decode µ-law → PCM16, then upsample 8 kHz → 16 kHz), and the
  reverse on the way out. A per-frame CPU + latency cost the spike must budget (R1).
- **L16** (linear PCM16, 8 kHz) — maps to PCM16 directly; only an 8 kHz ↔ 16 kHz
  resample is needed (much cheaper, no companding).

Pure stdlib only (``audioop`` was removed in Python 3.13; the runtime targets 3.14),
so the G.711 µ-law tables and the linear resampler are implemented here. Fidelity is
not the goal — this measures the *transcode budget*, so a simple linear resample is
enough. No new dependency (code-guidelines: library governance).
"""

from __future__ import annotations

import struct

_ULAW_BIAS = 0x84
_ULAW_CLIP = 32635
_SIGN_BIT = 0x80


def _linear_to_ulaw(sample: int) -> int:
    """One PCM16 sample -> one G.711 µ-law byte (CCITT G.711 reference)."""
    sign = _SIGN_BIT if sample < 0 else 0
    magnitude = min(abs(sample), _ULAW_CLIP) + _ULAW_BIAS
    exponent = _ulaw_exponent(magnitude)
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa)) & 0xFF


def _ulaw_exponent(magnitude: int) -> int:
    exponent = 7
    mask = 0x4000
    while exponent > 0 and not (magnitude & mask):
        exponent -= 1
        mask >>= 1
    return exponent


def _ulaw_to_linear(u_val: int) -> int:
    """One G.711 µ-law byte -> one PCM16 sample."""
    u_val = ~u_val & 0xFF
    mantissa = u_val & 0x0F
    exponent = (u_val >> 4) & 0x07
    magnitude = ((mantissa << 3) + _ULAW_BIAS) << exponent
    sample = magnitude - _ULAW_BIAS
    return -sample if (u_val & _SIGN_BIT) else sample


def pcm16_to_ulaw(pcm16: bytes) -> bytes:
    samples = struct.unpack(f"<{len(pcm16) // 2}h", pcm16)
    return bytes(_linear_to_ulaw(s) for s in samples)


def ulaw_to_pcm16(ulaw: bytes) -> bytes:
    samples = [_ulaw_to_linear(b) for b in ulaw]
    return struct.pack(f"<{len(samples)}h", *samples)


def upsample_2x(pcm16: bytes) -> bytes:
    """8 kHz -> 16 kHz by linear interpolation between adjacent samples."""
    samples = list(struct.unpack(f"<{len(pcm16) // 2}h", pcm16))
    out: list[int] = []
    for index, current in enumerate(samples):
        nxt = samples[index + 1] if index + 1 < len(samples) else current
        out.append(current)
        out.append((current + nxt) // 2)
    return struct.pack(f"<{len(out)}h", *out)


def downsample_2x(pcm16: bytes) -> bytes:
    """16 kHz -> 8 kHz by dropping every other sample (decimation)."""
    samples = struct.unpack(f"<{len(pcm16) // 2}h", pcm16)
    kept = samples[::2]
    return struct.pack(f"<{len(kept)}h", *kept)


def to_internal_pcm16(frame: bytes, codec: str) -> bytes:
    """Genesys wire frame (8 kHz PCMU or L16) -> internal PCM16 / 16 kHz."""
    pcm8k = ulaw_to_pcm16(frame) if codec == "PCMU" else frame
    return upsample_2x(pcm8k)


def from_internal_pcm16(pcm16_16k: bytes, codec: str) -> bytes:
    """Internal PCM16 / 16 kHz -> Genesys wire frame (8 kHz PCMU or L16)."""
    pcm8k = downsample_2x(pcm16_16k)
    return pcm16_to_ulaw(pcm8k) if codec == "PCMU" else pcm8k
