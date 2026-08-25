"""TASK-WEB-027: the transport-agnostic session factory builds the same
`StreamingVoiceSession` assembly for any transport, so WebRTC, the interim WebSocket
path and the future Genesys adapter are thin transport adapters over one session core.

These tests exercise the factory through a **non-WebRTC** stub transport (the AC's
"a fake/stub transport implementing the transport port"): no `SmallWebRTCConnection`,
no signaling — just `input()` / `output()`. WebRTC behaviour parity is covered by the
unchanged `tests/test_webrtc_signaling.py`.
"""

import unittest
from types import SimpleNamespace

from pipecat.processors.frame_processor import FrameProcessor  # noqa: E402

from voice_common.telemetry import TelemetryRecorder
from web_voice.envelope import ChannelEnvelope
from web_voice.session_factory import DEFAULT_SAMPLE_RATE, SessionFactory
from web_voice.streaming_runtime import StreamingVoiceSession
from web_voice.streaming_stt_processor import StreamingSttProcessor
from web_voice.streaming_tts_processor import StreamingTtsProcessor
from web_voice.utterance_aggregator import UtteranceAggregator


class _FakeIngress:
    provider_name = "fake-stt"


class _FakeEgress:
    provider_name = "fake-tts"


class _FakeBackend:
    pass


class _StubTransport:
    """A non-WebRTC transport: the factory only needs `input()` / `output()` for the
    pipeline (built later, at run). Any codec/sample-rate conversion is the adapter's
    job — the internal boundary the factory sees is already PCM16/16 kHz."""

    def __init__(self) -> None:
        self._in = FrameProcessor()
        self._out = FrameProcessor()

    def input(self) -> FrameProcessor:
        return self._in

    def output(self) -> FrameProcessor:
        return self._out


class SessionFactoryStreamingTest(unittest.TestCase):
    """A streaming-configured factory builds the streaming session over any transport."""

    def _factory(self) -> SessionFactory:
        return SessionFactory(
            ingress=_FakeIngress(),
            egress=_FakeEgress(),
            backend=_FakeBackend(),
            streaming_provider=SimpleNamespace(name="stt-default"),
            streaming_tts_provider=SimpleNamespace(name="tts-default"),
        )

    def test_stub_transport_builds_the_streaming_session_assembly(self) -> None:
        # GIVEN a non-WebRTC stub transport + a streaming-configured factory
        transport = _StubTransport()
        envelope = ChannelEnvelope.for_web_turn(language="fr")
        telemetry = TelemetryRecorder()
        # WHEN a session is built through the shared factory
        session, farewell = self._factory().build_session(transport, envelope, telemetry)
        # THEN the same StreamingVoiceSession assembly is produced (STT/TTS/telemetry/envelope)
        self.assertIsInstance(session, StreamingVoiceSession)
        self.assertIs(session._transport, transport)
        self.assertIs(session._envelope, envelope)
        self.assertIs(session._telemetry, telemetry)
        self.assertIsInstance(session._stt_processor, StreamingSttProcessor)
        self.assertIsInstance(session._tts_processor, StreamingTtsProcessor)
        # AND the farewell processor is wired into the pre-answer seam (TASK-WEB-010)
        self.assertIsNotNone(farewell)
        self.assertIn(farewell, session._pre_answer)

    def test_language_selects_the_per_language_provider(self) -> None:
        # GIVEN per-language providers -> THEN the envelope language drives selection
        factory = SessionFactory(
            ingress=_FakeIngress(),
            egress=_FakeEgress(),
            backend=_FakeBackend(),
            streaming_provider=SimpleNamespace(name="stt-default"),
            streaming_tts_provider=SimpleNamespace(name="tts-default"),
            streaming_providers_by_language={"en": SimpleNamespace(name="stt-en")},
            streaming_tts_providers_by_language={"en": SimpleNamespace(name="tts-en")},
        )
        en = ChannelEnvelope.for_web_turn(language="en")
        session, _ = factory.build_session(_StubTransport(), en, TelemetryRecorder())
        self.assertEqual(session._stt_processor._provider.name, "stt-en")


class SessionFactoryBatchTest(unittest.TestCase):
    """With no streaming provider the factory builds the batch aggregator path."""

    def test_stub_transport_builds_the_batch_session_at_pcm16_16k(self) -> None:
        # GIVEN a factory with no streaming provider (batch path)
        factory = SessionFactory(
            ingress=_FakeIngress(), egress=_FakeEgress(), backend=_FakeBackend()
        )
        # WHEN a session is built through the shared factory
        session, farewell = factory.build_session(
            _StubTransport(), ChannelEnvelope.for_web_turn(), TelemetryRecorder()
        )
        # THEN it is a batch StreamingVoiceSession (no streaming STT, no farewell)
        self.assertIsInstance(session, StreamingVoiceSession)
        self.assertIsNone(session._stt_processor)
        self.assertIsNone(farewell)
        # AND the internal audio boundary is PCM16 / 16 kHz (aggregator sample rate)
        self.assertEqual(DEFAULT_SAMPLE_RATE, 16000)
        aggregators = [p for p in session._pre_stt if isinstance(p, UtteranceAggregator)]
        self.assertEqual(len(aggregators), 1)
        self.assertEqual(aggregators[0]._sample_rate_hz, 16000)


if __name__ == "__main__":
    unittest.main()
