#!/usr/bin/env python3
"""LLM provider/model benchmark runner (TASK-BE-033, ADR-0045, ADR-0029 Direction A).

Drives the guarded ``POST /api/conversation/converse-stream`` path with the billing
fixture set for ONE already-configured candidate (the backend picks the provider/model
via ``LLM_PROVIDER`` + model env vars at startup), then writes a per-candidate JSON + MD.
Run it once per candidate (restart the backend between candidates so the provider swaps),
then merge the per-candidate JSONs into the ADR-0045 comparison table with ``compare.py``.

What it measures per turn (warm, isolated, sequential):
  - client-observed time-to-first-chunk (backend_first_token proxy, includes the network hop)
  - total answer time and chunk count
  - grounded flag + confidence + answer text (from the terminal ``done`` SSE event)
  - a DEC-002 heuristic: count of euro-amount-like mentions to flag for manual adjudication
Optionally (``--telemetry-log``) it tails the backend log across the run window and reads the
server-authoritative ``llm_first_token`` / ``backend_first_token`` slice durations.

Usage:
    python3 scripts/llm_benchmark/run_benchmark.py \
        --base-url http://localhost:8080 --label mistral-small --model mistral-small-latest \
        --reps 3 --telemetry-log /tmp/backend.log --out-dir scripts/llm_benchmark/reports
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
AMOUNT_RE = re.compile(r"\d[\d\s.,]*\s*(?:€|euros?|eur\b)", re.IGNORECASE)
_TELEMETRY_RE = re.compile(r"slice=(\S+)\b.*?\bduration_ms=(\d+)")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LLM provider/model benchmark harness (TASK-BE-033).")
    p.add_argument("--base-url", default="http://localhost:8080")
    p.add_argument("--label", required=True, help="Candidate label, e.g. 'mistral-small' (report filename + key).")
    p.add_argument("--model", default="", help="Model id string recorded in the report metadata.")
    p.add_argument("--fixtures", default=str(HERE / "billing_fixtures.json"))
    p.add_argument("--reps", type=int, default=3, help="Scored repetitions per question (warm).")
    p.add_argument("--warmup", type=int, default=1, help="Discarded warm-up turns before scoring.")
    p.add_argument("--language", default="fr", help="Forced answer language (fr|en).")
    p.add_argument("--api-key", default=None, help="Optional x-api-key header value.")
    p.add_argument("--telemetry-log", default=None,
                   help="Backend log file to tail for server-side llm_first_token/backend_first_token slices.")
    p.add_argument("--out-dir", default=str(HERE / "reports"))
    return p.parse_args()


def converse_stream(base_url: str, question: str, language: str, api_key: str | None) -> dict:
    """One /converse-stream turn. Returns per-turn timing + grounding, error is None on success."""
    payload = {
        "transcript": question,
        "conversation_id": "",
        "correlation_id": f"be033-{int(time.time()*1000)}",
        "channel": "benchmark",
        "language": language,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        headers["x-api-key"] = api_key
    req = urllib.request.Request(f"{base_url}/api/conversation/converse-stream", data=body,
                                 headers=headers, method="POST")
    start = time.perf_counter()
    try:
        return _consume_sse(req, start)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return _empty_turn(error=f"{type(exc).__name__}: {exc}")


def _consume_sse(req: urllib.request.Request, start: float) -> dict:
    turn = _empty_turn()
    event = ""
    with urllib.request.urlopen(req, timeout=60) as resp:
        for raw in resp:
            line = raw.decode("utf-8").rstrip("\n")
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                _apply_event(turn, event, line[len("data:"):].strip(), start)
    turn["total_ms"] = round((time.perf_counter() - start) * 1000, 1)
    return turn


def _apply_event(turn: dict, event: str, data: str, start: float) -> None:
    payload = json.loads(data) if data else {}
    if event == "chunk":
        if turn["ttfc_ms"] is None:
            turn["ttfc_ms"] = round((time.perf_counter() - start) * 1000, 1)
        turn["num_chunks"] += 1
    elif event == "done":
        turn["grounded"] = bool(payload.get("grounded"))
        turn["confidence"] = payload.get("confidence")
        turn["answer_text"] = str(payload.get("text") or "")
    elif event == "error":
        turn["error"] = f"{payload.get('error_code') or 'ERR'}: {payload.get('message') or data}"


def _empty_turn(error: str | None = None) -> dict:
    return {"ttfc_ms": None, "total_ms": None, "num_chunks": 0, "grounded": False,
            "confidence": None, "answer_text": "", "error": error}


def percentiles(values: list[float]) -> dict:
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return {"n": 0, "p50": None, "p95": None, "min": None, "max": None, "mean": None}
    return {"n": len(clean), "p50": _pct(clean, 50), "p95": _pct(clean, 95),
            "min": clean[0], "max": clean[-1], "mean": round(statistics.fmean(clean), 1)}


def _pct(sorted_values: list[float], pct: int) -> float:
    # Nearest-rank percentile (matches streaming_latency_report.py convention).
    rank = max(1, (pct * len(sorted_values) + 99) // 100)
    return round(sorted_values[min(rank, len(sorted_values)) - 1], 1)


def run_turns(args: argparse.Namespace, questions: list[dict]) -> list[dict]:
    turns: list[dict] = []
    for _ in range(max(0, args.warmup)):
        converse_stream(args.base_url, questions[0]["question"], args.language, args.api_key)
    for rep in range(args.reps):
        for q in questions:
            turn = converse_stream(args.base_url, q["question"], args.language, args.api_key)
            turn.update(question_id=q["id"], rep=rep,
                        amount_mentions=len(AMOUNT_RE.findall(turn["answer_text"])),
                        answer_chars=len(turn["answer_text"]))
            turn.pop("answer_text_full", None)
            turns.append(turn)
    return turns


def read_server_slices(log_path: str, from_offset: int) -> dict:
    """Parse llm_first_token / backend_first_token duration_ms from the log tail written this run."""
    slices: dict[str, list[float]] = {"llm_first_token": [], "backend_first_token": []}
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(from_offset)
            for line in fh:
                if "[TELEMETRY]" not in line:
                    continue
                m = _TELEMETRY_RE.search(line)
                if m and m.group(1) in slices:
                    slices[m.group(1)].append(float(m.group(2)))
    except OSError:
        return {}
    return {name: percentiles(vals) for name, vals in slices.items()}


def aggregate(turns: list[dict], server_slices: dict) -> dict:
    scored = [t for t in turns if not t["error"]]
    confidences = [t["confidence"] for t in scored if t["confidence"] is not None]
    agg = {
        "turns_total": len(turns),
        "turns_scored": len(scored),
        "errors": sum(1 for t in turns if t["error"]),
        "grounded_rate": round(sum(1 for t in scored if t["grounded"]) / len(scored), 3) if scored else 0.0,
        "confidence_mean": round(statistics.fmean(confidences), 4) if confidences else None,
        "amount_mentions_total": sum(t["amount_mentions"] for t in scored),
        "client_ttfc_ms": percentiles([t["ttfc_ms"] for t in scored]),
        "client_total_ms": percentiles([t["total_ms"] for t in scored]),
    }
    if server_slices:
        agg["server_llm_first_token_ms"] = server_slices.get("llm_first_token")
        agg["server_backend_first_token_ms"] = server_slices.get("backend_first_token")
    return agg


def to_json(args: argparse.Namespace, spec: dict, turns: list[dict], agg: dict) -> dict:
    return {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "ticket": "TASK-BE-033",
        "candidate": {"label": args.label, "model": args.model},
        "base_url": args.base_url,
        "fixtures_version": spec.get("version"),
        "reps": args.reps,
        "warmup": args.warmup,
        "language": args.language,
        "aggregate": agg,
        "turns": turns,
    }


def build_markdown(args: argparse.Namespace, spec: dict, agg: dict) -> str:
    ttfc, total = agg["client_ttfc_ms"], agg["client_total_ms"]
    lines = [
        f"# LLM benchmark — candidate `{args.label}` (TASK-BE-033 / ADR-0045)",
        "",
        f"- **Model:** `{args.model or 'n/a'}` | **Base URL:** {args.base_url}",
        f"- **Fixtures:** billing v{spec.get('version')} ({len(spec['questions'])} questions × {args.reps} reps)",
        f"- **Date:** {dt.date.today().isoformat()}",
        "",
        "> Text-in through the guarded `converse-stream` path (real retrieval + guardrails). "
        "Client time-to-first-chunk is a `backend_first_token` proxy (includes the network hop); "
        "prefer the server-side slices when a telemetry log is supplied.",
        "",
        "## Aggregate",
        "",
        "| Metric | p50 | p95 |",
        "|---|---:|---:|",
        f"| client time-to-first-chunk (ms) | {ttfc['p50']} | {ttfc['p95']} |",
        f"| client total answer (ms) | {total['p50']} | {total['p95']} |",
    ]
    for key, label in (("server_llm_first_token_ms", "server llm_first_token (ms)"),
                       ("server_backend_first_token_ms", "server backend_first_token (ms)")):
        s = agg.get(key)
        if s and s.get("n"):
            lines.append(f"| {label} | {s['p50']} | {s['p95']} |")
    lines += [
        "",
        f"- **Grounded rate:** {agg['grounded_rate']} ({agg['turns_scored']} scored turns)",
        f"- **Mean confidence:** {agg['confidence_mean']}",
        f"- **Amount-mention flags (manual DEC-002 review):** {agg['amount_mentions_total']}",
        f"- **Errors:** {agg['errors']}",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    spec = json.loads(Path(args.fixtures).read_text(encoding="utf-8"))
    questions = spec["questions"]
    offset = os.path.getsize(args.telemetry_log) if args.telemetry_log and os.path.exists(args.telemetry_log) else 0
    turns = run_turns(args, questions)
    server_slices = read_server_slices(args.telemetry_log, offset) if args.telemetry_log else {}
    agg = aggregate(turns, server_slices)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"bench-{args.label}.json").write_text(
        json.dumps(to_json(args, spec, turns, agg), ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"bench-{args.label}.md").write_text(build_markdown(args, spec, agg), encoding="utf-8")
    ttfc = agg["client_ttfc_ms"]
    print(f"[{args.label}] ttfc p50={ttfc['p50']} p95={ttfc['p95']} ms | "
          f"grounded={agg['grounded_rate']} conf={agg['confidence_mean']} "
          f"errors={agg['errors']} -> {out_dir}")
    if agg["errors"]:
        first = next(t["error"] for t in turns if t["error"])
        print(f"WARNING: {agg['errors']} turn error(s); first: {first}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
