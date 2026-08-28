"""Synthetic-audio latency harness for the Genesys spike (TASK-WEB-025 / DEC-014).

Drives N synthetic voice round trips through the throwaway AudioHook prototype for each
Genesys wire codec (PCMU, L16), decomposes the transport + transcode legs (p50/p95),
re-scores the full mouth-to-ear against the ADR-0029 gate, and probes the pilot
concurrency target (3 concurrent sessions, DEC-014) on a 1-vCPU-class runtime. It uses
synthetic / non-PII audio only and reuses the real ``voice_common`` telemetry +
deterministic ``traceparent`` (Genesys conversationId -> one OpenTelemetry trace).

Run:  .venv/bin/python spikes/genesys_audiohook/harness.py --turns 30
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from voice_common.trace_context import derive_traceparent  # noqa: E402

from spikes.genesys_audiohook.audiohook_prototype import AudioHookSessionPrototype, Runtime  # noqa: E402
from spikes.genesys_audiohook.genesys_legs import per_leg_report, transport_overhead_samples  # noqa: E402
from spikes.genesys_audiohook.rescore import DEFAULT_BASE_MOUTH_TO_EAR_P95_MS, rescore  # noqa: E402
from spikes.genesys_audiohook.synthetic_audio import synthetic_pcm16_16k, synthetic_wire_frames  # noqa: E402

CODECS = ("PCMU", "L16")


def synthetic_runtime(answer_ms: int) -> Runtime:
    """Stub bot runtime: returns synthetic PCM16 (STT/backend/TTS are reused, not called)."""
    audio = synthetic_pcm16_16k(answer_ms, seed=7)
    return lambda _pcm16_in: audio


def run_sample(*, codec: str, turns: int, caller_ms: int, answer_ms: int) -> TelemetryRecorder:
    telemetry = TelemetryRecorder()
    runtime = synthetic_runtime(answer_ms)
    for turn in range(turns):
        conversation_id = f"spike-{codec}-{turn}"
        frames = synthetic_wire_frames(caller_ms, codec, seed=turn + 1)
        AudioHookSessionPrototype(telemetry, codec=codec, conversation_id=conversation_id).run_turn(frames, runtime)
    return telemetry


def codec_report(telemetry: TelemetryRecorder, *, codec: str, base_p95_ms: float | None) -> dict[str, Any]:
    spans = telemetry.spans()
    overhead = transport_overhead_samples(spans)
    return {
        "codec": codec,
        "per_leg": per_leg_report(spans),
        "transport_overhead_samples": len(overhead),
        "adr_0029_rescore": rescore(overhead, base_mouth_to_ear_p95_ms=base_p95_ms),
        "example_traceparent": derive_traceparent(f"spike-{codec}-0"),
    }


def _one_session(codec: str, caller_ms: int, answer_ms: int, index: int) -> None:
    telemetry = TelemetryRecorder()
    frames = synthetic_wire_frames(caller_ms, codec, seed=index + 1)
    AudioHookSessionPrototype(
        telemetry, codec=codec, conversation_id=f"conc-{codec}-{index}"
    ).run_turn(frames, synthetic_runtime(answer_ms))


def concurrency_probe(*, codec: str, sessions: int, caller_ms: int, answer_ms: int) -> dict[str, Any]:
    """Run `sessions` prototype sessions concurrently; report the 1-vCPU serialization."""
    sequential = _timed(lambda: _one_session(codec, caller_ms, answer_ms, 0))
    concurrent = _timed(lambda: _run_concurrent(codec, sessions, caller_ms, answer_ms))
    ratio = round(concurrent / sequential, 2) if sequential else None
    return {
        "target_sessions": sessions,
        "codec": codec,
        "single_session_ms": round(sequential, 3),
        "concurrent_wall_ms": round(concurrent, 3),
        "serialization_ratio": ratio,
        "note": _concurrency_note(sessions, ratio),
    }


def _run_concurrent(codec: str, sessions: int, caller_ms: int, answer_ms: int) -> None:
    with ThreadPoolExecutor(max_workers=sessions) as pool:
        futures = [pool.submit(_one_session, codec, caller_ms, answer_ms, i) for i in range(sessions)]
        for future in futures:
            future.result()


def _timed(action) -> float:
    start = time.perf_counter()
    action()
    return (time.perf_counter() - start) * 1000


def _concurrency_note(sessions: int, ratio: float | None) -> str:
    if ratio is None:
        return "no single-session baseline to compare"
    return (
        f"{sessions} concurrent sessions took {ratio}x a single session's wall time. Pure-Python "
        "transcode is CPU-bound (GIL-serialized), so on a 1-vCPU-class runtime concurrent Genesys "
        "sessions ~serialize the transcode CPU; ratio ~= sessions confirms the R6 1-vCPU concern "
        "(a production transcode would move to a C codec / native lib)."
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    base = None if args.base_mouth_to_ear_ms < 0 else args.base_mouth_to_ear_ms
    codecs = [
        codec_report(
            run_sample(codec=codec, turns=args.turns, caller_ms=args.caller_ms, answer_ms=args.answer_ms),
            codec=codec,
            base_p95_ms=base,
        )
        for codec in CODECS
    ]
    return {
        "spike": "TASK-WEB-025",
        "audio": "synthetic / non-PII only (DEC-014 synthetic-first)",
        "sample": {"turns_per_codec": args.turns, "caller_ms": args.caller_ms, "answer_ms": args.answer_ms},
        "base_mouth_to_ear_p95_ms": base,
        "codecs": codecs,
        "concurrency": concurrency_probe(
            codec="PCMU", sessions=args.concurrency, caller_ms=args.caller_ms, answer_ms=args.answer_ms
        ),
        "blocked_on_live_org": [
            "genesys_ingress / architect_fork / genesys_egress cloud legs (TASK-INFRA-012)",
            "codec confirmed end-to-end on the pilot org (PCMU vs L16)",
            "15-minute cap vs the worst-case billing journey",
            "PII-audio residency/egress sign-off (Security/Compliance, OQ-006)",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesys Audio Connector synthetic latency harness (TASK-WEB-025)")
    parser.add_argument("--turns", type=int, default=30, help="synthetic round trips per codec")
    parser.add_argument("--caller-ms", type=int, default=2000, help="synthetic caller utterance length (ms)")
    parser.add_argument("--answer-ms", type=int, default=4000, help="synthetic bot answer length (ms)")
    parser.add_argument("--concurrency", type=int, default=3, help="pilot concurrency target (DEC-014)")
    parser.add_argument(
        "--base-mouth-to-ear-ms",
        type=float,
        default=DEFAULT_BASE_MOUTH_TO_EAR_P95_MS,
        help="in-house WS-path mouth-to-ear p95 the Genesys legs stack on (<0 to omit)",
    )
    args = parser.parse_args()
    print(json.dumps(build_report(args), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
