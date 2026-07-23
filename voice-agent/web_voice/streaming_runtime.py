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
from collections.abc import Sequence
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
        pre_stt: Sequence[FrameProcessor] = (),
        pre_output: Sequence[FrameProcessor] = (),
        stt_detects_end_of_turn: bool = True,
        stt_processor: FrameProcessor | None = None,
        tts_processor: FrameProcessor | None = None,
    ) -> None:
        self._transport = transport
        self._ingress = ingress
        self._egress = egress
        self._envelope = envelope
        self._backend = backend or StubBackendAdapter()
        self._telemetry = telemetry
        # When set (streaming STT path, TASK-STT-010), this processor is the STT
        # stage: it consumes continuous audio, streams to the provider and emits the
        # final TranscriptionFrame itself, so the batch SttFrameProcessor + utterance
        # aggregator are not built.
        self._stt_processor = stt_processor
        # When set (streaming TTS path, TASK-WEB-004), this processor is the TTS
        # stage: it streams the answer to the provider and pushes TTSAudioRawFrames
        # incrementally, so the batch TtsFrameProcessor is not built.
        self._tts_processor = tts_processor
        # False when a pre-STT utterance aggregator owns incremental end-of-turn
        # detection (streaming path, TASK-STT-012); the batch detector in the
        # ingress is then skipped so the voice.end_of_turn span is not duplicated.
        self._stt_detects_end_of_turn = stt_detects_end_of_turn
        # Processors inserted between transport.input() and STT. A continuous
        # transport (WebRTC) needs an utterance aggregator here to turn streamed
        # audio into whole-utterance frames; the batch fake transport passes none.
        self._pre_stt = list(pre_stt)
        # Processors inserted between TTS and transport.output(). The WebRTC path puts
        # the ChannelEgressProbe here to measure runtime egress of the first audio
        # frame (TASK-WEB-014); the in-memory fake transport passes none, so the
        # streaming spike keeps its egress-as-gap behaviour unchanged.
        self._pre_output = list(pre_output)
        self._task: Any = None
        # Number of times the runner was awaited; the single-loop guarantee is
        # `run_count == 1` for a whole session (asserted by the tests, RF-012).
        self.run_count = 0

    def _build_pipeline(self) -> Pipeline:
        stt = self._stt_processor or SttFrameProcessor(
            self._ingress,
            self._envelope,
            self._telemetry,
            detect_end_of_turn=self._stt_detects_end_of_turn,
        )
        answer = AnswerProcessor(self._backend, self._envelope, self._telemetry)
        tts = self._tts_processor or TtsFrameProcessor(
            self._egress, self._envelope, self._telemetry
        )
        return Pipeline(
            [
                self._transport.input(),
                *self._pre_stt,
                stt,
                answer,
                tts,
                *self._pre_output,
                self._transport.output(),
            ]
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

    async def drain(self) -> None:
        """Graceful end-of-call flush (TASK-WEB-008): queue an `EndFrame` so a trailing
        partial utterance (customer still mid-speech at hangup) is finalized as a
        `client_stop` end-of-turn and transcribed before teardown, instead of being
        silently dropped.

        Unlike `stop()` (which cancels the task and discards pending work), `drain()`
        lets the pipeline process the `EndFrame` end to end — the utterance aggregator
        / streaming STT run their `finish()` path, emit the `voice.end_of_turn` span and
        the final transcript. `run()` then returns on its own. Safe to call when nothing
        is pending or the task has already finished. A genuinely abrupt network drop may
        still lose the tail; this covers the graceful `closed`/`disconnected` case.
        """
        if self._task is not None and not self._task.has_finished():
            await self._task.stop_when_done()

    async def stop(self) -> None:
        """Graceful teardown: cancel the running task (transport drop / session end)."""
        if self._task is not None:
            await self._task.cancel()
