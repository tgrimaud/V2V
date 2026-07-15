"""Tests for the single long-lived event-loop streaming session
(Sprint 6 / TASK-WEB-007, spike).

Drives `transport.input -> stt -> answer -> tts -> transport.output` with an
in-memory fake transport (no `aiortc` / ICE), proving:
- the runner is awaited exactly once for the whole session (single loop, RF-012);
- STT / answer / TTS are reused and audio flows out the transport;
- teardown on transport drop cancels the task gracefully.
"""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

from pipecat.frames.frames import (  # noqa: E402
    Frame,
    InputAudioRawFrame,
    StartFrame,
    TTSAudioRawFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # noqa: E402

from conversation_backend import AnswerOutcome, AnswerRequest, AnswerResult  # noqa: E402
from stt_validation.models import SttOutcome, TranscriptResult  # noqa: E402
from tts_synthesis.models import SynthesisResult, TtsOutcome  # noqa: E402
from web_voice.streaming_runtime import StreamingVoiceSession  # noqa: E402


def _transcript(outcome: SttOutcome, text: str = "") -> TranscriptResult:
    return TranscriptResult(
        transcript=text,
        provider="fake-stt",
        outcome=outcome,
        duration_ms=1.0,
        stt_request_ms=1.0,
        correlation_id="corr-1",
    )


def _envelope() -> SimpleNamespace:
    return SimpleNamespace(
        channel="web_voice",
        conversation_id="conv-1",
        correlation_id="corr-1",
        external_session_id="s",
    )


class _FakeIngress:
    def __init__(self, result: TranscriptResult) -> None:
        self._result = result
        self.calls: list[tuple] = []

    def transcribe_turn(self, audio, envelope, telemetry=None, *, received_ms=None):
        self.calls.append((audio, envelope, telemetry, received_ms))
        return self._result


class _FakeBackend:
    name = "fake-backend"

    def answer(self, request: AnswerRequest) -> AnswerResult:
        return AnswerResult(
            text="ANSWERED:" + request.transcript,
            provider=self.name,
            outcome=AnswerOutcome.SUCCESS,
            correlation_id=request.correlation_id,
        )


class _FakeEgress:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def synthesize_turn(self, text, envelope, telemetry=None):
        self.calls.append((text, envelope, telemetry))
        result = SynthesisResult(
            audio=b"AUDIO:" + text.encode("utf-8"),
            provider="fake-tts",
            outcome=TtsOutcome.SUCCESS,
            duration_ms=1.0,
            tts_request_ms=1.0,
            correlation_id="corr-1",
            audio_format="pcm_16000",
        )
        return SimpleNamespace(result=result, wav=b"WAV:" + text.encode("utf-8"))


class _FakeInput(FrameProcessor):
    """Source: on StartFrame, emits the queued utterance frames downstream.

    The session stays live afterwards (like a held WebRTC call); teardown is
    transport-driven via `session.stop()`, mirroring a `disconnected`/`closed` event.
    """

    def __init__(self, audio_frames) -> None:
        super().__init__()
        self._audio_frames = audio_frames
        self.started = asyncio.Event()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            self.started.set()
            for audio in self._audio_frames:
                await self.push_frame(audio, FrameDirection.DOWNSTREAM)


class _FakeOutput(FrameProcessor):
    """Sink: captures the synthesized PCM the TTS stage pushes downstream."""

    def __init__(self) -> None:
        super().__init__()
        self.audio = bytearray()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            self.audio.extend(frame.audio)
        await self.push_frame(frame, direction)


class _FakeTransport:
    def __init__(self, audio_frames) -> None:
        self._input = _FakeInput(audio_frames)
        self._output = _FakeOutput()

    def input(self) -> FrameProcessor:
        return self._input

    def output(self) -> FrameProcessor:
        return self._output

    @property
    def captured_audio(self) -> bytes:
        return bytes(self._output.audio)


async def _wait_for(predicate, *, timeout: float = 10.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while not predicate():
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(0.02)


def _audio_frame(payload: bytes) -> InputAudioRawFrame:
    return InputAudioRawFrame(audio=payload, sample_rate=16000, num_channels=1)


class StreamingVoiceSessionTest(unittest.IsolatedAsyncioTestCase):
    async def test_drives_the_loop_once_and_flows_audio_out_the_transport(self) -> None:
        # GIVEN a transport feeding one utterance, and STT/answer/TTS fakes
        transport = _FakeTransport([_audio_frame(b"\x01\x02")])
        egress = _FakeEgress()
        session = StreamingVoiceSession(
            transport,
            ingress=_FakeIngress(_transcript(SttOutcome.SUCCESS, text="hello")),
            egress=egress,
            envelope=_envelope(),
            backend=_FakeBackend(),
        )
        # WHEN the session runs and the utterance flows end to end on the one loop
        run_task = asyncio.create_task(session.run())
        try:
            await _wait_for(lambda: transport.captured_audio != b"")
        finally:
            await session.stop()
            await asyncio.wait_for(run_task, timeout=10)
        # THEN the runner was awaited exactly once (single long-lived loop, RF-012)
        self.assertEqual(session.run_count, 1)
        # AND the backend answer (not the transcript) was synthesized out the transport
        self.assertEqual(egress.calls[0][0], "ANSWERED:hello")
        self.assertEqual(transport.captured_audio, b"AUDIO:ANSWERED:hello")

    async def test_stop_tears_down_gracefully_on_transport_drop(self) -> None:
        # GIVEN a live session (a held call, no utterance completed yet)
        transport = _FakeTransport([_audio_frame(b"\x01")])
        session = StreamingVoiceSession(
            transport,
            ingress=_FakeIngress(_transcript(SttOutcome.SUCCESS, text="hi")),
            egress=_FakeEgress(),
            envelope=_envelope(),
            backend=_FakeBackend(),
        )
        run_task = asyncio.create_task(session.run())
        await asyncio.wait_for(transport.input().started.wait(), timeout=10)
        # WHEN the transport drops and we stop the session
        await session.stop()
        # THEN run() returns without raising (graceful teardown), still one loop
        await asyncio.wait_for(run_task, timeout=10)
        self.assertEqual(session.run_count, 1)


if __name__ == "__main__":
    unittest.main()
