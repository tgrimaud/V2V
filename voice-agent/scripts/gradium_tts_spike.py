"""ST-1 spike: probe the live Gradium TTS WebSocket contract.

Disposable exploration script (TASK-WEB-002). It opens the Gradium TTS
WebSocket, runs the setup -> text -> end_of_stream handshake, and reports the
observed contract (message shapes, chunk format, first-chunk latency) so the
real GradiumTtsProvider can be built against verified behaviour instead of an
assumption. It never prints the API key.

Run: python3 scripts/gradium_tts_spike.py ["text to synthesize"]
Reads GRADIUM_API_KEY / GRADIUM_VOICE_ID from the environment or ../.env.
"""

import asyncio
import base64
import json
import struct
import sys
import time
from pathlib import Path

import websockets

TTS_URL = "wss://api.gradium.ai/api/speech/tts"
SAMPLE_RATE = 16000
DEFAULT_TEXT = "Bonjour, ceci est un test de synthèse vocale Gradium."


def load_env() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    import os

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, 1,
        sample_rate, sample_rate * 2, 2, 16,
        b"data", len(pcm),
    )
    return header + pcm


async def run(text: str) -> int:
    import os

    api_key = os.environ.get("GRADIUM_API_KEY")
    if not api_key:
        print("GRADIUM_API_KEY not set (env or ../.env)", file=sys.stderr)
        return 2
    voice_id = os.environ.get("GRADIUM_VOICE_ID", "default")
    output_format = os.environ.get("GRADIUM_OUTPUT_FORMAT", "pcm_16000")

    print(f"[spike] voice_id={voice_id} output_format={output_format} chars={len(text)}")
    start = time.perf_counter()
    first_chunk_ms: float | None = None
    chunks: list[bytes] = []
    message_types: dict[str, int] = {}

    async with websockets.connect(TTS_URL, additional_headers={"x-api-key": api_key}) as ws:
        await ws.send(json.dumps({
            "type": "setup",
            "model_name": "default",
            "voice_id": voice_id,
            "output_format": output_format,
        }))
        ready_raw = await ws.recv()
        ready = json.loads(ready_raw)
        print(f"[spike] setup response: {ready}")
        if ready.get("type") != "ready":
            print("[spike] setup did NOT return type=ready — voice_id/output_format likely invalid")
            return 1

        await ws.send(json.dumps({"type": "text", "text": text}))
        await ws.send(json.dumps({"type": "end_of_stream"}))

        async for raw in ws:
            data = json.loads(raw)
            mtype = str(data.get("type"))
            message_types[mtype] = message_types.get(mtype, 0) + 1
            if mtype == "audio":
                audio_b64 = data.get("audio", "")
                if audio_b64:
                    if first_chunk_ms is None:
                        first_chunk_ms = (time.perf_counter() - start) * 1000
                    chunks.append(base64.b64decode(audio_b64))
            elif mtype == "end_of_stream":
                break

    total_ms = (time.perf_counter() - start) * 1000
    pcm = b"".join(chunks)
    print("\n===== Gradium TTS contract (observed) =====")
    print(f"message types seen : {message_types}")
    print(f"audio chunks       : {len(chunks)}")
    print(f"total PCM bytes     : {len(pcm)}  (~{len(pcm) / 2 / SAMPLE_RATE:.2f}s at {SAMPLE_RATE}Hz mono 16-bit)")
    print(f"first-chunk latency: {first_chunk_ms:.0f} ms" if first_chunk_ms else "first-chunk latency: n/a")
    print(f"total latency       : {total_ms:.0f} ms")

    if pcm:
        out = Path("/tmp/gradium_tts_spike.wav")
        out.write_bytes(pcm_to_wav(pcm))
        print(f"saved WAV          : {out}  (open to listen)")
        return 0
    print("[spike] no audio produced")
    return 1


def main() -> int:
    load_env()
    text = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TEXT
    return asyncio.run(run(text))


if __name__ == "__main__":
    raise SystemExit(main())
