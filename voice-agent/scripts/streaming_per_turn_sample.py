"""Multi-turn streaming per-turn telemetry sample (TASK-WEB-017, feeds ADR-0018/0029).

The streaming counterpart to `turn_latency_sample.py`, focused on the per-turn
identity added in TASK-WEB-017. It composes the real streaming processors
    source -> StreamingSttProcessor -> AnswerProcessor -> StreamingTtsProcessor -> sink
on ONE call (one TelemetryRecorder, one correlation id), drives several end-of-turn
detections in a row, and prints ONE server-style telemetry dump line
(`{"spans": [...], "events": [...], "metrics": [...]}`) per call.

Piping the output into `streaming_latency_report.py` yields the `per_turn` section
with one row per turn under a single correlation id — the offline, repeatable proof
that a multi-turn streaming call is separable turn by turn. STT/TTS providers are
fakes and the backend is the deterministic stub, so absolute durations are
fixture-fast; real p50/p95/p99 still require the live Gradium/Mistral stack over a
warm WebRTC sample (captured separately in the QA report).

Run:
    .venv/bin/python scripts/streaming_per_turn_sample.py --turns 3 --calls 2 \
        | .venv/bin/python scripts/streaming_latency_report.py --channel web \
            --provider fake-streaming --warm
"""

import argparse
import asyncio
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipecat.frames.frames import EndFrame, Frame, InputAudioRawFrame  # noqa: E402
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402

from conversation_backend import StubBackendAdapter  # noqa: E402
from stt_validation.streaming import FinalTranscript, PartialTranscript  # noqa: E402
from tts_synthesis.streaming import AudioChunk  # noqa: E402
from voice_common.telemetry import TelemetryRecorder  # noqa: E402
from voice_pipeline.answer import AnswerProcessor  # noqa: E402
from web_voice.end_of_turn import DEFAULT_AMPLITUDE_THRESHOLD, StreamingEndOfTurnDetector  # noqa: E402
from web_voice.envelope import ChannelEnvelope  # noqa: E402
from web_voice.streaming_stt_processor import StreamingSttProcessor  # noqa: E402
from web_voice.streaming_tts_processor import StreamingTtsProcessor  # noqa: E402

SAMPLE_RATE = 16000
FRAME_BYTES = (SAMPLE_RATE * 20 // 1000) * 2


def _speech_frame() -> InputAudioRawFrame:
    pcm = (5000).to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)
    return InputAudioRawFrame(audio=pcm, sample_rate=SAMPLE_RATE, num_channels=1)


def _silence_frame() -> InputAudioRawFrame:
    return InputAudioRawFrame(audio=b"\x00" * FRAME_BYTES, sample_rate=SAMPLE_RATE, num_channels=1)


class _FakeSttSession:
    def __init__(self, partials, final_text):
        self._queued = list(partials)
        self._released: list = []
        self._final_text = final_text

    async def send_audio(self, pcm):
        if self._queued:
            self._released.append(self._queued.pop(0))

    def poll_partials(self):
        out, self._released = self._released, []
        return out

    async def finish(self):
        return None

    async def wait_final(self):
        return FinalTranscript(self._final_text)

    async def aclose(self):
        return None


class _MultiSttProvider:
    name = "fake-streaming-stt"

    def __init__(self, turns):
        self._sessions = [
            _FakeSttSession([PartialTranscript("partial")], f"question numero {i + 1}")
            for i in range(turns)
        ]

    async def open(self):
        return self._sessions.pop(0)


class _FakeTtsSession:
    def __init__(self):
        self._chunks = [AudioChunk(b"\x01\x02"), AudioChunk(b"\x03\x04")]

    async def synthesize(self, text):
        return None

    async def stream(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self):
        return None


class _MultiTtsProvider:
    name = "fake-streaming-tts"

    async def open(self):
        return _FakeTtsSession()


class _Sink(FrameProcessor):
    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)


async def _run_call(correlation_id: str, turns: int) -> TelemetryRecorder:
    telemetry = TelemetryRecorder()
    envelope = ChannelEnvelope.for_web_turn(correlation_id=correlation_id)
    detector = StreamingEndOfTurnDetector(
        sample_rate_hz=SAMPLE_RATE,
        silence_window_ms=100,
        amplitude_threshold=DEFAULT_AMPLITUDE_THRESHOLD,
        min_utterance_ms=20,
    )
    stt = StreamingSttProcessor(_MultiSttProvider(turns), envelope, telemetry, detector=detector)
    answer = AnswerProcessor(StubBackendAdapter(), envelope, telemetry)
    tts = StreamingTtsProcessor(_MultiTtsProvider(), envelope, telemetry, prewarm=False)

    one_turn = [_speech_frame()] * 3 + [_silence_frame()] * 10
    sink = _Sink()
    pipeline = Pipeline([stt, answer, tts, sink])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask

        task = PipelineTask(
            pipeline, params=PipelineParams(), enable_rtvi=False,
            enable_turn_tracking=False, cancel_on_idle_timeout=False, check_dangling_tasks=False,
        )
        run = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        # Pace the turns: let each turn's TTS finish before the next turn's speech
        # onset, otherwise the next utterance triggers barge-in and cancels the
        # in-flight TTS (no first-audio for that turn). Real calls are time-separated.
        for _ in range(turns):
            await task.queue_frames(list(one_turn))
            await asyncio.sleep(0.4)
        await task.queue_frames([EndFrame()])
        await asyncio.wait_for(run, timeout=15)
    return telemetry


def _dump_line(telemetry: TelemetryRecorder) -> str:
    payload = {
        "spans": [span.__dict__ for span in telemetry.spans()],
        "events": [event.__dict__ for event in telemetry.events()],
        "metrics": [metric.__dict__ for metric in telemetry.metrics()],
    }
    return json.dumps(payload, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-turn streaming per-turn telemetry sample (TASK-WEB-017)")
    parser.add_argument("--turns", type=int, default=3, help="end-of-turns per call")
    parser.add_argument("--calls", type=int, default=1, help="number of streaming calls to emit")
    args = parser.parse_args()
    for i in range(args.calls):
        telemetry = asyncio.run(_run_call(f"per-turn-sample-{i}", args.turns))
        print(_dump_line(telemetry))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
