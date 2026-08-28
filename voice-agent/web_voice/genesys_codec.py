"""Native (numpy-vectorized) Genesys Audio Connector codec (TASK-WEB-041, ADR-0049).

Genesys Audio Connector offers two wire codecs on the 8 kHz IVR channel:

- **L16** — linear PCM16; only an 8 kHz <-> 16 kHz resample to reach the internal
  PCM16/16 kHz boundary (ADR-0043). Cheapest; the spike (TASK-WEB-025) recommends it.
- **PCMU** — G.711 mu-law; needs companding + resample. Heavier, so L16 is preferred.

The TASK-WEB-025 spike proved the *shape* with a pure-stdlib transcode but flagged R6:
a pure-Python per-sample loop is CPU-bound and, holding the GIL for its whole duration,
**serializes** (~2.96x wall time at concurrency 3 on 1 vCPU). This production codec fixes
that by vectorizing every hot path with **numpy**, which releases the GIL during its C
array operations, so concurrent sessions no longer serialize on the transcode.

numpy is not a new dependency: it is already a transitive requirement of the runtime
(``opencv-python`` -> ``numpy``), so adopting it here adds **zero** new wheels (the same
"already transitive" reasoning as aiohttp in ADR-0047). It is BSD-licensed and ubiquitous.

Byte order: L16 is treated as little-endian PCM16 to match the spike's internal boundary;
confirming the pilot org's on-wire byte order is a live-org item (TASK-INFRA-012).
"""

from __future__ import annotations

import numpy as np

PCMU = "PCMU"
L16 = "L16"
SUPPORTED_CODECS: tuple[str, ...] = (L16, PCMU)
# Spike (TASK-WEB-025) recommendation: prefer L16 end to end (resample only).
DEFAULT_CODEC = L16

_PCM16 = "<i2"
_ULAW_BIAS = 0x84
_ULAW_CLIP = 32635
_SIGN_BIT = 0x80
_INT16_OFFSET = 32768


def _reference_linear_to_ulaw(sample: int) -> int:
    """One PCM16 sample -> one G.711 mu-law byte (CCITT G.711 reference)."""
    sign = _SIGN_BIT if sample < 0 else 0
    magnitude = min(abs(sample), _ULAW_CLIP) + _ULAW_BIAS
    exponent = 7
    mask = 0x4000
    while exponent > 0 and not (magnitude & mask):
        exponent -= 1
        mask >>= 1
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa)) & 0xFF


def _reference_ulaw_to_linear(u_val: int) -> int:
    """One G.711 mu-law byte -> one PCM16 sample (CCITT G.711 reference)."""
    u_val = ~u_val & 0xFF
    mantissa = u_val & 0x0F
    exponent = (u_val >> 4) & 0x07
    magnitude = ((mantissa << 3) + _ULAW_BIAS) << exponent
    sample = magnitude - _ULAW_BIAS
    return -sample if (u_val & _SIGN_BIT) else sample


# Built ONCE at import from the G.711 reference so runtime transcode is pure vectorized
# LUT indexing (GIL-released), never a per-sample Python loop. _ENCODE_LUT maps every
# int16 (offset by +32768) to its mu-law byte; _DECODE_LUT maps each mu-law byte back.
_ENCODE_LUT = np.array(
    [_reference_linear_to_ulaw(value - _INT16_OFFSET) for value in range(65536)],
    dtype=np.uint8,
)
_DECODE_LUT = np.array(
    [_reference_ulaw_to_linear(value) for value in range(256)], dtype=np.int16
)


def _as_int16(pcm16: bytes) -> np.ndarray:
    """View PCM16 bytes as an int16 array, dropping a trailing odd byte defensively."""
    usable = len(pcm16) - (len(pcm16) % 2)
    return np.frombuffer(pcm16[:usable], dtype=_PCM16)


def pcm16_to_ulaw(pcm16: bytes) -> bytes:
    """PCM16 (little-endian) -> G.711 mu-law bytes, vectorized via the encode LUT."""
    samples = _as_int16(pcm16).astype(np.int32) + _INT16_OFFSET
    return _ENCODE_LUT.take(samples).tobytes()


def ulaw_to_pcm16(ulaw: bytes) -> bytes:
    """G.711 mu-law bytes -> PCM16 (little-endian), vectorized via the decode LUT."""
    indices = np.frombuffer(ulaw, dtype=np.uint8)
    return _DECODE_LUT.take(indices).astype(_PCM16).tobytes()


def upsample_2x(pcm16: bytes) -> bytes:
    """8 kHz -> 16 kHz by linear interpolation between adjacent samples (vectorized)."""
    samples = _as_int16(pcm16).astype(np.int32)
    if samples.size == 0:
        return b""
    nxt = np.empty_like(samples)
    nxt[:-1] = samples[1:]
    nxt[-1] = samples[-1]
    out = np.empty(samples.size * 2, dtype=np.int32)
    out[0::2] = samples
    out[1::2] = (samples + nxt) // 2
    return out.astype(_PCM16).tobytes()


def downsample_2x(pcm16: bytes) -> bytes:
    """16 kHz -> 8 kHz by decimation (drop every other sample), vectorized."""
    return np.ascontiguousarray(_as_int16(pcm16)[::2]).tobytes()


def to_internal_pcm16(frame: bytes, codec: str = DEFAULT_CODEC) -> bytes:
    """Genesys wire frame (8 kHz PCMU or L16) -> internal PCM16 / 16 kHz."""
    _require_supported(codec)
    pcm8k = ulaw_to_pcm16(frame) if codec == PCMU else frame
    return upsample_2x(pcm8k)


def from_internal_pcm16(pcm16_16k: bytes, codec: str = DEFAULT_CODEC) -> bytes:
    """Internal PCM16 / 16 kHz -> Genesys wire frame (8 kHz PCMU or L16)."""
    _require_supported(codec)
    pcm8k = downsample_2x(pcm16_16k)
    return pcm16_to_ulaw(pcm8k) if codec == PCMU else pcm8k


def _require_supported(codec: str) -> None:
    if codec not in SUPPORTED_CODECS:
        raise ValueError(f"unsupported Genesys codec {codec!r} (supported: {SUPPORTED_CODECS})")
