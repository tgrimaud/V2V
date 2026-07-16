"""Live Gradium streaming-STT spike (TASK-STT-010).

Confirms the WebSocket ASR contract (wss://api.gradium.ai/api/speech/asr) and
captures the streaming latency profile that justifies moving off batch STT:

  - time-to-first-partial : from first audio chunk to the first `text` message
  - post-end-of-turn tail : from `flush`/`end_of_stream` to the final transcript
    (this is the latency the customer perceives after they stop speaking; batch
    STT pays the full clip-length processing cost here instead)

Usage:
  ./.venv/bin/python scripts/gradium_stt_stream_spike.py fixtures/long/invoice-breakdown.pcm

The API key is read from ../.env (GRADIUM_API_KEY) and never printed.
"""

import asyncio
import base64
import json
import re
import sys
import time
from pathlib import Path

import websockets

WS_URL = "wss://api.gradium.ai/api/speech/asr"
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
FRAME_SAMPLES = 1920  # server default frame_size; ~120 ms @ 16 kHz
REAL_TIME_PACE_S = FRAME_SAMPLES / SAMPLE_RATE


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"([A-Z_]+)=(.*)", line.strip())
        if match:
            env[match.group(1)] = match.group(2).strip()
    return env


async def run(pcm_path: Path, api_key: str, language: str) -> None:
    audio = pcm_path.read_bytes()
    utterance_s = len(audio) / BYTES_PER_SAMPLE / SAMPLE_RATE
    chunk_bytes = FRAME_SAMPLES * BYTES_PER_SAMPLE

    clock = {"t0": None, "flush": None}
    first_partial: list[float] = []
    parts: list[str] = []
    final_t: list[float] = []
    done = asyncio.Event()

    def rel(now: float) -> float:
        return now - clock["t0"] if clock["t0"] else 0.0

    async with websockets.connect(
        WS_URL, additional_headers={"x-api-key": api_key}, max_size=None
    ) as ws:
        await ws.send(json.dumps({
            "type": "setup",
            "model_name": "default",
            "input_format": "pcm_16000",
            "json_config": {"language": language},
        }))

        async def receiver() -> None:
            async for raw in ws:
                now = time.monotonic()
                msg = json.loads(raw)
                typ = msg.get("type")
                if typ == "ready":
                    print(f"ready: frame_size={msg.get('frame_size')} delay_in_frames={msg.get('delay_in_frames')}")
                elif typ == "text":
                    if not first_partial and clock["t0"]:
                        first_partial.append(now - clock["t0"])
                    parts.append(str(msg.get("text", "")))
                    print(f"[{rel(now):5.2f}s] text: {msg.get('text')!r} (start_s={msg.get('start_s')})")
                elif typ == "end_text":
                    print(f"[{rel(now):5.2f}s] end_text stop_s={msg.get('stop_s')}")
                elif typ == "flushed":
                    print(f"[{rel(now):5.2f}s] flushed id={msg.get('flush_id')}")
                elif typ == "end_of_stream":
                    final_t.append(rel(now))
                    print(f"[{rel(now):5.2f}s] end_of_stream")
                    done.set()
                    return
                elif typ == "error":
                    print(f"[{rel(now):5.2f}s] ERROR: {msg}")
                    done.set()
                    return

        recv_task = asyncio.create_task(receiver())
        clock["t0"] = time.monotonic()
        for offset in range(0, len(audio), chunk_bytes):
            payload = base64.b64encode(audio[offset:offset + chunk_bytes]).decode("ascii")
            await ws.send(json.dumps({"type": "audio", "audio": payload}))
            await asyncio.sleep(REAL_TIME_PACE_S)  # simulate a live mic

        audio_done = time.monotonic() - clock["t0"]
        clock["flush"] = time.monotonic()
        await ws.send(json.dumps({"type": "flush", "flush_id": 1}))
        await ws.send(json.dumps({"type": "end_of_stream"}))

        try:
            await asyncio.wait_for(done.wait(), timeout=30.0)
        finally:
            recv_task.cancel()

    ttfp = f"{first_partial[0]:.2f}s" if first_partial else "n/a"
    final_rel = final_t[0] if final_t else None
    tail = (final_rel - (clock["flush"] - clock["t0"])) if final_rel is not None else None
    print("\n=== SUMMARY (streaming) ===")
    print(f"utterance length      : {utterance_s:.2f}s")
    print(f"audio fully sent at   : {audio_done:.2f}s (real-time paced)")
    print(f"time-to-first-partial : {ttfp}")
    print(f"time-to-final         : {final_rel:.2f}s" if final_rel is not None else "time-to-final         : n/a")
    print(f"post-end-of-turn tail : {tail:.2f}s" if tail is not None else "post-end-of-turn tail : n/a")
    print(f"transcript            : {' '.join(p for p in parts if p).strip()!r}")


def main() -> int:
    pcm_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/long/invoice-breakdown.pcm")
    env = load_env(Path(__file__).resolve().parents[2] / ".env")
    api_key = env.get("GRADIUM_API_KEY")
    if not api_key:
        print("GRADIUM_API_KEY missing in .env", file=sys.stderr)
        return 1
    language = env.get("GRADIUM_LANGUAGE") or "fr"
    asyncio.run(run(pcm_path, api_key, language))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
