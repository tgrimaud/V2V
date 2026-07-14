"""A/B parity harness: stdlib vs pipecat runtime (Sprint 4 / TASK-WEB-005, ST-8).

Runs the same input through both voice runtimes and checks two things:
  1. Parity: both runtimes produce byte-identical WAV output (they must, since both
     delegate to the same STT/TTS runners).
  2. Overhead: the per-runtime latency, so the Pipecat wrapper's cost over the stdlib
     path is visible (this is a batch migration, so parity is the goal, not speed).

Providers are held constant (a canned STT stub + the deterministic fixture TTS), so
the ONLY variable is the runtime. This makes the harness a repeatable, offline
comparison artifact supporting the ADR-0016 "stdlib kept as comparison path" role.

Run: `.venv/bin/python scripts/ab_parity.py [--iterations N]`
Exit code is non-zero if any turn diverges between runtimes.
"""

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tts_synthesis import FixtureTtsProvider  # noqa: E402
from web_voice import ChannelEnvelope, WebVoiceEgress, WebVoiceIngress  # noqa: E402
from web_voice.runtime import PipecatTurnProcessor, StdlibTurnProcessor  # noqa: E402

DEFAULT_ITERATIONS = 20
DEFAULT_AUDIO = b"\x01\x02\x03\x04" * 256  # arbitrary non-empty PCM16 buffer


class _StubStt:
    """Canned STT so the harness runs offline and only the runtime varies."""

    name = "stub-stt"

    def transcribe(self, audio_path) -> str:  # noqa: ANN001
        return "bonjour le monde"


@dataclass(frozen=True)
class ParityReport:
    iterations: int
    mismatches: int
    stdlib_ms: list[float]
    pipecat_ms: list[float]

    @property
    def all_identical(self) -> bool:
        return self.mismatches == 0

    def summary(self) -> dict:
        return {
            "iterations": self.iterations,
            "all_identical": self.all_identical,
            "mismatches": self.mismatches,
            "stdlib": _latency_stats(self.stdlib_ms),
            "pipecat": _latency_stats(self.pipecat_ms),
        }


def run_ab_parity(iterations: int = DEFAULT_ITERATIONS, audio: bytes = DEFAULT_AUDIO) -> ParityReport:
    ingress = WebVoiceIngress(_StubStt())
    egress = WebVoiceEgress(FixtureTtsProvider())
    stdlib = StdlibTurnProcessor(ingress, egress)
    pipecat = PipecatTurnProcessor(ingress, egress)

    mismatches = 0
    stdlib_ms: list[float] = []
    pipecat_ms: list[float] = []
    for i in range(iterations):
        envelope = ChannelEnvelope.for_web_turn(correlation_id=f"ab-{i}")
        stdlib_wav, stdlib_dt = _timed_turn(stdlib, audio, envelope)
        pipecat_wav, pipecat_dt = _timed_turn(pipecat, audio, envelope)
        stdlib_ms.append(stdlib_dt)
        pipecat_ms.append(pipecat_dt)
        if stdlib_wav != pipecat_wav:
            mismatches += 1
    return ParityReport(iterations, mismatches, stdlib_ms, pipecat_ms)


def _timed_turn(processor, audio: bytes, envelope: ChannelEnvelope) -> tuple[bytes | None, float]:
    start = time.perf_counter()
    result = processor.run_turn(audio, envelope)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    wav = result.tts_response.wav if result.tts_response else None
    return wav, elapsed_ms


def _latency_stats(samples: list[float]) -> dict:
    if not samples:
        return {"count": 0}
    ordered = sorted(samples)
    return {
        "count": len(samples),
        "mean_ms": round(statistics.mean(samples), 3),
        "p50_ms": round(_percentile(ordered, 50), 3),
        "p95_ms": round(_percentile(ordered, 95), 3),
    }


def _percentile(ordered: list[float], pct: float) -> float:
    # Nearest-rank percentile (matches the LatencyReport convention in voice_common).
    rank = max(1, (pct * len(ordered) + 99) // 100)
    return ordered[int(rank) - 1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare stdlib vs pipecat voice runtimes")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    args = parser.parse_args()

    report = run_ab_parity(args.iterations)
    summary = report.summary()
    print("A/B parity (stdlib vs pipecat), providers held constant:")
    print(f"  iterations    : {summary['iterations']}")
    print(f"  all_identical : {summary['all_identical']}")
    print(f"  mismatches    : {summary['mismatches']}")
    print(f"  stdlib  latency: {summary['stdlib']}")
    print(f"  pipecat latency: {summary['pipecat']}")
    if not report.all_identical:
        print("PARITY FAILED: runtimes diverged", file=sys.stderr)
        return 1
    print("PARITY OK: both runtimes produce byte-identical WAV")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
