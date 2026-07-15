"""Single long-lived event-loop voice session (Sprint 6 / TASK-WEB-007, spike).

The batch runtime (`PipecatTurnProcessor`) spins a fresh event loop +
`PipelineTask`/`PipelineRunner` and `asyncio.run(...)` **per turn** (RF-012). The
streaming path builds the pipeline **once** and awaits the runner **once** for the
whole call, so the transport, STT, backend answer and TTS all live on one loop.

This module is transport-agnostic: the transport is injected (duck-typed
`StreamingTransport`) so the same session drives the real `SmallWebRTCTransport`
(via `webrtc_support.load_webrtc_transport`) in production and an in-memory fake in
tests — no `aiortc`/ICE needed to validate the single-loop drive and teardown. See
`docs/qa/webrtc-transport-spike.md`.

The STT / answer / TTS `FrameProcessor`s from Sprint 4/5 are reused unchanged, so
the conversation contract, degraded fallback and US-036 telemetry carry over.
"""

import warnings
from typing import Any, Protocol

from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameProcessor

from conversation_backend import BackendAnswerPort, StubBackendAdapter
from voice_pipeline.answer import AnswerProcessor
from voice_pipeline.stt_service import SttFrameProcessor, SttIngress
from voice_pipeline.tts_service import TtsEgress, TtsFrameProcessor


class StreamingTransport(Protocol):
    """The transport seam the streaming session drives.

    Both `SmallWebRTCTransport` and the in-memory fake expose `input()` / `output()`
    returning the source / sink `FrameProcessor` for the pipeline.
    """

    def input(self) -> FrameProcessor: ...

    def output(self) -> FrameProcessor: ...


class StreamingVoiceSession:
    """Drives `transport.input -> stt -> answer -> tts -> transport.output` once.

    `run()` awaits the `PipelineRunner` a single time for the whole session; `stop()`
    cancels the task for a graceful teardown on transport drop.
    """

    def __init__(
        self,
        transport: StreamingTransport,
        *,
        ingress: SttIngress,
        egress: TtsEgress,
        envelope: Any,
        backend: BackendAnswerPort | None = None,
        telemetry: Any = None,
    ) -> None:
        self._transport = transport
        self._ingress = ingress
        self._egress = egress
        self._envelope = envelope
        self._backend = backend or StubBackendAdapter()
        self._telemetry = telemetry
        self._task: Any = None
        # Number of times the runner was awaited; the single-loop guarantee is
        # `run_count == 1` for a whole session (asserted by the tests, RF-012).
        self.run_count = 0

    def _build_pipeline(self) -> Pipeline:
        stt = SttFrameProcessor(self._ingress, self._envelope, self._telemetry)
        answer = AnswerProcessor(self._backend, self._envelope, self._telemetry)
        tts = TtsFrameProcessor(self._egress, self._envelope, self._telemetry)
        return Pipeline(
            [self._transport.input(), stt, answer, tts, self._transport.output()]
        )

    async def run(self) -> None:
        """Build the pipeline once and await the runner once (single long-lived loop)."""
        pipeline = self._build_pipeline()
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message=r".*deprecated.*", category=DeprecationWarning
            )
            from pipecat.pipeline.runner import PipelineRunner
            from pipecat.pipeline.task import PipelineParams, PipelineTask

            self._task = PipelineTask(
                pipeline,
                params=PipelineParams(),
                enable_rtvi=False,
                enable_turn_tracking=False,
                cancel_on_idle_timeout=False,
                check_dangling_tasks=False,
            )
            runner = PipelineRunner(handle_sigint=False)
            self.run_count += 1
            await runner.run(self._task)

    async def stop(self) -> None:
        """Graceful teardown: cancel the running task (transport drop / session end)."""
        if self._task is not None:
            await self._task.cancel()
