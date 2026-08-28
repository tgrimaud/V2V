"""Synthetic, non-PII audio for the Genesys spike harness (TASK-WEB-025 / DEC-014).

The spike is **synthetic-first**: it must never touch real customer audio. This
generates deterministic low-amplitude noise as PCM16 / 16 kHz (the internal boundary)
and encodes it to the Genesys wire codec. Low-amplitude noise (never pure digital
silence) mirrors a live mic's ambient floor — the lesson from TASK-WEB-007, where an
Opus-DTX pure-silence pad produced no packets and an energy detector never flushed.
Here it just keeps the transcode/timing path realistic; no real speech is needed to
budget the transport + transcode legs.
"""

from __future__ import annotations

import random
import struct

from .transcode import from_internal_pcm16

INTERNAL_SAMPLE_RATE = 16000
WIRE_SAMPLE_RATE = 8000
_NOISE_PEAK = 300  # << the ~1000 energy-onset threshold: ambient-floor, not speech


def synthetic_pcm16_16k(duration_ms: int, *, seed: int = 1) -> bytes:
    """Deterministic low-amplitude PCM16 / 16 kHz noise of the given duration."""
    rng = random.Random(seed)
    sample_count = INTERNAL_SAMPLE_RATE * duration_ms // 1000
    samples = [rng.randint(-_NOISE_PEAK, _NOISE_PEAK) for _ in range(sample_count)]
    return struct.pack(f"<{len(samples)}h", *samples)


def synthetic_wire_frames(duration_ms: int, codec: str, *, frame_ms: int = 20, seed: int = 1) -> list[bytes]:
    """Synthetic caller audio as Genesys wire frames (8 kHz PCMU or L16 chunks)."""
    pcm16_16k = synthetic_pcm16_16k(duration_ms, seed=seed)
    bytes_per_frame = INTERNAL_SAMPLE_RATE * frame_ms // 1000 * 2
    frames: list[bytes] = []
    for start in range(0, len(pcm16_16k), bytes_per_frame):
        chunk = pcm16_16k[start:start + bytes_per_frame]
        if chunk:
            frames.append(from_internal_pcm16(chunk, codec))
    return frames
