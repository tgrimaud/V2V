"""Full-turn per-slice latency sample (TASK-WEB-003-G, feeds US-036).

Runs N complete voice turns (audio -> STT -> backend answer -> TTS -> egress)
through a runtime, accumulating every span on one `TelemetryRecorder`, and prints
the US-036 `PipelineTimingReport`: p50/p95/p99 per canonical slice, with the
backend slice now measured (TASK-WEB-003-D/E) and the safe fallback path (degraded
mode, TASK-WEB-003-F) exercisable via `--degraded`.

Providers are held constant (a canned STT stub + the deterministic fixture TTS +
the stub backend), so this is a repeatable OFFLINE artifact: the absolute numbers
are fixture-fast and only prove the slices are wired and measured end to end. Real
p50/p95/p99 require the live Gradium STT/TTS and a real conversation endpoint
(`--provider gradium`, `--backend http`) and are captured in the QA report.

Run: `.venv/bin/python scripts/turn_latency_sample.py [--iterations N] [--runtime stdlib|pipecat] [--degraded]`
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation_backend import AnswerRequest, AnswerResult, StubBackendAdapter  # noqa: E402
from tts_synthesis import FixtureTtsProvider  # noqa: E402
from voice_common.pipeline_timing import PipelineTimingReport  # noqa: E402
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from web_voice import ChannelEnvelope, WebVoiceEgress, WebVoiceIngress  # noqa: E402
from web_voice.runtime import build_turn_processor  # noqa: E402

DEFAULT_ITERATIONS = 30
DEFAULT_AUDIO = b"\x01\x02\x03\x04" * 256  # arbitrary non-empty PCM16 buffer


class _StubStt:
    name = "stub-stt"

    def transcribe(self, audio_path) -> str:  # noqa: ANN001
        return "bonjour pourquoi ma facture augmente ce mois"


class _UnavailableBackend:
    """Always fails, to exercise the degraded (safe fallback) path end to end."""

    name = "http-backend"

    def answer(self, request: AnswerRequest) -> AnswerResult:
        raise RuntimeError("conversation endpoint is unreachable")


def run_sample(iterations: int, runtime: str, degraded: bool) -> dict:
    ingress = WebVoiceIngress(_StubStt())
    egress = WebVoiceEgress(FixtureTtsProvider())
    backend = _UnavailableBackend() if degraded else StubBackendAdapter()
    processor = build_turn_processor(runtime, ingress, egress, backend)
    telemetry = TelemetryRecorder()
    for i in range(iterations):
        envelope = ChannelEnvelope.for_web_turn(correlation_id=f"lat-{i}")
        result = processor.run_turn(DEFAULT_AUDIO, envelope, telemetry)
        if result.tts_response is not None:
            processor.record_egress(result.tts_response, envelope, telemetry, sent_ms=0.0)
    report = PipelineTimingReport.from_spans(telemetry.spans())
    return {
        "runtime": runtime,
        "iterations": iterations,
        "backend": backend.name,
        "degraded": degraded,
        "report": report.to_dict(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Full-turn per-slice latency sample (US-036)")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--runtime", choices=("stdlib", "pipecat"), default="stdlib")
    parser.add_argument("--degraded", action="store_true", help="exercise the safe-fallback path")
    args = parser.parse_args()
    print(json.dumps(run_sample(args.iterations, args.runtime, args.degraded), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
