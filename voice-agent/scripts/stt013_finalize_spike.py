"""TASK-STT-013 spike: is the STT post-EOT finalize tail avoidable?

The TASK-WEB-009 warm baseline put `time_to_first_audio` p95 at 1698 ms, dominated
by the STT post-end-of-turn finalize tail (p95 ~1389 ms). The final transcript is
just the concatenation of the `text` partials Gradium already streamed, so the
hypothesis is: **commit the answer on the last stable partial at end-of-turn**
instead of waiting for the server's terminal `end_of_stream`, and let the
authoritative final confirm/correct asynchronously.

This spike streams a real clip to Gradium (real-time paced, like a live mic),
marks the moment we send `flush` + `end_of_stream` (= end-of-turn), and measures:

  - pure_tail_ms        : flush -> end_of_stream round-trip (the latency we'd save)
  - last_text_after_ms  : flush -> last `text` message (0 if all text arrived before flush)
  - transcript_at_flush : what we already have when we commit on the last partial
  - transcript_final    : the authoritative final
  - lost_tail_words     : words the final adds that commit-on-flush would miss

If pure_tail is large AND lost_tail_words is small, commit-on-last-partial is a
free (or cheap) latency win. If the final adds material trailing words, the
tradeoff is accuracy vs latency and needs a product call.

Usage:
  ./.venv/bin/python scripts/stt013_finalize_spike.py [clip.pcm] [--runs N]
The API key is read from ../.env (GRADIUM_API_KEY) and never printed.
"""

import argparse
import asyncio
import base64
import json
import re
import sys
import time
from dataclasses import dataclass, field
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


@dataclass
class TurnMeasurement:
    pure_tail_ms: float | None = None
    last_text_after_ms: float = 0.0
    end_text_after_ms: float | None = None
    flushed_after_ms: float | None = None
    transcript_at_flush: str = ""
    transcript_final: str = ""
    texts_before_flush: int = 0
    texts_after_flush: int = 0
    parts: list[str] = field(default_factory=list)

    @property
    def lost_tail_words(self) -> int:
        final_words = self.transcript_final.split()
        kept_words = self.transcript_at_flush.split()
        return max(0, len(final_words) - len(kept_words))


async def run_once(audio: bytes, api_key: str, language: str) -> TurnMeasurement:
    chunk_bytes = FRAME_SAMPLES * BYTES_PER_SAMPLE
    m = TurnMeasurement()
    t0 = {"v": 0.0}
    flush_at = {"v": None}
    parts_before: list[str] = []
    done = asyncio.Event()

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
                if typ == "text":
                    text = str(msg.get("text", ""))
                    m.parts.append(text)
                    if flush_at["v"] is None:
                        m.texts_before_flush += 1
                        parts_before.append(text)
                    else:
                        m.texts_after_flush += 1
                        m.last_text_after_ms = (now - flush_at["v"]) * 1000.0
                elif typ == "end_text":
                    if flush_at["v"] is not None:
                        m.end_text_after_ms = (now - flush_at["v"]) * 1000.0
                elif typ == "flushed":
                    if flush_at["v"] is not None:
                        m.flushed_after_ms = (now - flush_at["v"]) * 1000.0
                elif typ == "end_of_stream":
                    if flush_at["v"] is not None:
                        m.pure_tail_ms = (now - flush_at["v"]) * 1000.0
                    done.set()
                    return
                elif typ == "error":
                    done.set()
                    return

        recv_task = asyncio.create_task(receiver())
        t0["v"] = time.monotonic()
        for offset in range(0, len(audio), chunk_bytes):
            payload = base64.b64encode(audio[offset:offset + chunk_bytes]).decode("ascii")
            await ws.send(json.dumps({"type": "audio", "audio": payload}))
            await asyncio.sleep(REAL_TIME_PACE_S)  # simulate a live mic

        flush_at["v"] = time.monotonic()
        await ws.send(json.dumps({"type": "flush", "flush_id": 1}))
        await ws.send(json.dumps({"type": "end_of_stream"}))
        try:
            await asyncio.wait_for(done.wait(), timeout=30.0)
        finally:
            recv_task.cancel()

    m.transcript_at_flush = " ".join(p for p in parts_before if p).strip()
    m.transcript_final = " ".join(p for p in m.parts if p).strip()
    return m


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round((p / 100.0) * (len(ordered) - 1))))
    return ordered[k]


async def run(clip: Path, api_key: str, language: str, runs: int) -> None:
    audio = clip.read_bytes()
    utterance_s = len(audio) / BYTES_PER_SAMPLE / SAMPLE_RATE
    print(f"clip={clip.name} length={utterance_s:.2f}s runs={runs}\n")
    tails: list[float] = []
    lost: list[int] = []
    for i in range(runs):
        m = await run_once(audio, api_key, language)
        if m.pure_tail_ms is not None:
            tails.append(m.pure_tail_ms)
        lost.append(m.lost_tail_words)
        et = f"{m.end_text_after_ms:.1f}" if m.end_text_after_ms is not None else "n/a"
        fl = f"{m.flushed_after_ms:.1f}" if m.flushed_after_ms is not None else "n/a"
        print(
            f"run {i+1}: pure_tail={m.pure_tail_ms:6.1f}ms  "
            f"last_text@={m.last_text_after_ms:6.1f}ms  "
            f"end_text@={et}ms  flushed@={fl}ms  "
            f"lost_tail_words={m.lost_tail_words}"
        )
        print(f"        at_flush: {m.transcript_at_flush!r}")
        print(f"        final   : {m.transcript_final!r}")
        await asyncio.sleep(1.0)

    print("\n=== SUMMARY (pure flush->end_of_stream tail) ===")
    print(f"pure_tail p50/p95 : {_pct(tails,50):.1f} / {_pct(tails,95):.1f} ms  (n={len(tails)})")
    print(f"lost_tail_words   : min={min(lost)} max={max(lost)} "
          f"(runs with 0 lost = {sum(1 for x in lost if x == 0)}/{len(lost)})")
    print("\nInterpretation: pure_tail is the latency commit-on-last-partial would")
    print("save on time_to_first_audio; lost_tail_words is the accuracy cost.")


def main() -> int:
    parser = argparse.ArgumentParser(description="TASK-STT-013 finalize-tail spike")
    parser.add_argument("clip", nargs="?", default="fixtures/long/invoice-breakdown.pcm")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    env = load_env(Path(__file__).resolve().parents[2] / ".env")
    api_key = env.get("GRADIUM_API_KEY")
    if not api_key:
        print("GRADIUM_API_KEY missing in .env", file=sys.stderr)
        return 1
    language = env.get("GRADIUM_LANGUAGE") or "fr"
    asyncio.run(run(Path(args.clip), api_key, language, args.runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
