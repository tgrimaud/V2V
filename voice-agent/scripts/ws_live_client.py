"""Headless WebSocket voice client for TASK-WEB-031 latency evidence.

The streaming WS loop cannot be driven in-process (it needs a real socket + live
STT/TTS/backend), so — exactly like the WebRTC path — its per-slice telemetry is
emitted server-side: `WebSocketSignalingService` prints one JSON dump line per call
on client disconnect (`{"spans": [...], "events": [...], "metrics": [...],
"pipeline_timing": {...}}`). This client drives a real `wss` turn so that dump is
produced, then the sample is scored with `scripts/streaming_latency_report.py`.

Wire protocol (ADR-0043 / `web_voice/websocket_framing.py`):
- text JSON control frames: `{"type": "open", "language": "fr"}` → server replies `opened`;
- binary messages are PCM16 mono 16 kHz audio (straight-through, no codec);
- bot audio comes back as binary; `barge_in` / `call_end` come back as JSON control.

Capture a warm sample (server up with real providers), then score it:

    # terminal 1 — capture server stderr (the per-call dumps land here)
    set -a; . ../.env; set +a
    .venv/bin/python -m web_voice.server --websocket on --stt-mode streaming \\
        --tts-mode streaming --backend http 2> /tmp/ws-telemetry.jsonl

    # terminal 2 — drive N warm turns (one call each; disconnect emits the dump)
    for i in $(seq 1 12); do
      .venv/bin/python scripts/ws_live_client.py --url ws://127.0.0.1:8091 \\
        --audio fixtures/long/billing-question.pcm --language fr --hold 12
    done

    # score the sample against the ADR-0029 gate
    .venv/bin/python scripts/streaming_latency_report.py \\
        --input /tmp/ws-telemetry.jsonl --channel web --provider gradium-streaming --warm
"""

import argparse
import asyncio
import json
import math
import struct
import sys
import time
import wave
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_FRAME_MS = 20
# Received-audio RMS above which a bot binary frame counts as real speech (int16 scale),
# separating the first audible answer frame from any silence/keepalive.
AUDIBLE_RMS_THRESHOLD = 200.0
# Trailing real silence appended after the clip so the energy end-of-turn detector sees
# sustained silence and flushes the utterance. Unlike WebRTC/Opus (DTX sends no packets on
# digital silence), the raw-PCM WS path transmits every frame, so zeros are fine here.
TRAILING_SILENCE_MS = 800


def build_open_frame(language: str | None) -> str:
    """The JSON `open` control frame; `language` is omitted when not declared."""
    message: dict[str, object] = {"type": "open"}
    if language:
        message["language"] = language
    return json.dumps(message)


CLOSE_FRAME = json.dumps({"type": "close"})


def load_pcm(path: str) -> bytes:
    """Load raw PCM16 mono 16 kHz bytes from a `.pcm` (raw) or `.wav` (header stripped) file."""
    if path.lower().endswith(".wav"):
        with wave.open(path, "rb") as handle:
            return handle.readframes(handle.getnframes())
    return Path(path).read_bytes()


def frame_bytes(sample_rate: int, frame_ms: int) -> int:
    """Byte length of one PCM16 mono frame (2 bytes/sample)."""
    return int(sample_rate * frame_ms / 1000) * 2


def iter_pcm_frames(pcm: bytes, chunk: int) -> Iterator[bytes]:
    """Yield fixed-size PCM16 frames; a trailing short frame is padded with silence."""
    for start in range(0, len(pcm), chunk):
        frame = pcm[start : start + chunk]
        if len(frame) < chunk:
            frame = frame + b"\x00" * (chunk - len(frame))
        yield frame


def silence_frames(count: int, chunk: int) -> Iterator[bytes]:
    """`count` frames of digital silence (zeros) of `chunk` bytes each."""
    silent = b"\x00" * chunk
    for _ in range(count):
        yield silent


def frame_rms(pcm: bytes) -> float:
    """RMS amplitude of a little-endian PCM16 frame (0.0 for an empty/odd frame)."""
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", pcm[: n * 2])
    return math.sqrt(sum(s * s for s in samples) / n)


async def run(
    url: str,
    audio: str,
    *,
    language: str | None = "fr",
    hold: float = 12.0,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    frame_ms: int = DEFAULT_FRAME_MS,
) -> int:
    import websockets

    chunk = frame_bytes(sample_rate, frame_ms)
    pcm = load_pcm(audio)
    clip_frames = list(iter_pcm_frames(pcm, chunk))
    trailing = list(silence_frames(max(1, TRAILING_SILENCE_MS // frame_ms), chunk))
    first_audible = {"at": None}

    async with websockets.connect(url, max_size=None) as ws:
        await ws.send(build_open_frame(language))
        drain = asyncio.ensure_future(_drain(ws, first_audible))
        # Stream the clip in real time (one frame per frame_ms) so the server's
        # end-of-turn detector sees a realistic cadence, then trailing silence.
        for frame in clip_frames:
            await ws.send(frame)
            await asyncio.sleep(frame_ms / 1000)
        stop_speaking_at = time.monotonic()
        for frame in trailing:
            await ws.send(frame)
            await asyncio.sleep(frame_ms / 1000)
        # Hold the call open so STT→backend→TTS completes and audio streams back.
        await asyncio.sleep(hold)
        await ws.send(CLOSE_FRAME)
        drain.cancel()

    _report(first_audible["at"], stop_speaking_at)
    return 0


async def _drain(ws, first_audible: dict) -> None:
    """Receive bot frames; record the first audible (above-threshold) binary frame."""
    try:
        async for message in ws:
            if isinstance(message, (bytes, bytearray)) and first_audible["at"] is None:
                if frame_rms(bytes(message)) >= AUDIBLE_RMS_THRESHOLD:
                    first_audible["at"] = time.monotonic()
    except asyncio.CancelledError:
        return


def _report(first_audible_at: float | None, stop_speaking_at: float) -> None:
    """Log a client-observed mouth-to-ear proxy (server dump carries the per-slice truth)."""
    if first_audible_at is None:
        print("first_audible_bot_audio: none (no above-threshold frame received)")
        return
    mouth_to_ear_ms = round((first_audible_at - stop_speaking_at) * 1000, 1)
    print("mouth_to_ear_proxy_ms:", mouth_to_ear_ms)


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless WebSocket voice evidence client")
    parser.add_argument("--url", default="ws://127.0.0.1:8091")
    parser.add_argument("--audio", required=True, help="PCM16/16k .pcm (or .wav) to stream")
    parser.add_argument("--language", default="fr")
    parser.add_argument("--hold", type=float, default=12.0, help="seconds to keep the call open")
    args = parser.parse_args()
    return asyncio.run(run(args.url, args.audio, language=args.language, hold=args.hold))


if __name__ == "__main__":
    raise SystemExit(main())
