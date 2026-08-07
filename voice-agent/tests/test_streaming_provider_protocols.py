"""Streaming provider protocols + provider-keyed factory (TASK-WEB-023).

Proves the streaming (latency-critical) STT/TTS path is no longer locked to Gradium:
- the Gradium streaming providers/sessions conform to the explicit protocols;
- a fake provider (no network, no Gradium) also conforms;
- the provider factory selects a streaming provider by name via a registry, so a fake
  vendor registered at runtime drives the WebRTC selection in `server.py` — with no
  `== GRADIUM` branch — and unknown / batch-only providers cleanly fall back.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

VOICE_AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VOICE_AGENT_ROOT))

import stt_validation.provider_factory as stt_factory  # noqa: E402
import tts_synthesis.provider_factory as tts_factory  # noqa: E402
from stt_validation.streaming import (  # noqa: E402
    FinalTranscript,
    GradiumStreamingSession,
    GradiumStreamingSttProvider,
    PartialTranscript,
    StreamingSttProvider,
    StreamingSttSession,
)
from tts_synthesis.streaming import (  # noqa: E402
    GradiumStreamingTtsProvider,
    GradiumStreamingTtsSession,
    StreamingTtsProvider,
    StreamingTtsSession,
)

FAKE_VENDOR = "fakevendor"


class _FakeStreamingSttSession:
    async def send_audio(self, pcm: bytes) -> None: ...

    def poll_partials(self) -> list[PartialTranscript]:
        return []

    async def finish(self) -> None: ...

    async def wait_final(self) -> FinalTranscript:
        return FinalTranscript("bonjour")

    async def aclose(self) -> None: ...


class _FakeStreamingSttProvider:
    name = "fake-streaming-stt"

    def __init__(self, *, language: str | None = None) -> None:
        self.language = language

    async def open(self) -> _FakeStreamingSttSession:
        return _FakeStreamingSttSession()


class _FakeStreamingTtsSession:
    async def synthesize(self, text: str) -> None: ...

    async def stream(self):
        for chunk in ():  # empty async generator (no network)
            yield chunk

    async def aclose(self) -> None: ...


class _FakeStreamingTtsProvider:
    name = "fake-streaming-tts"
    audio_format = "pcm_16000"

    def __init__(self, *, voice_id: str | None = None) -> None:
        self.voice_id = voice_id

    async def open(self) -> _FakeStreamingTtsSession:
        return _FakeStreamingTtsSession()


class StreamingProtocolConformanceTest(unittest.TestCase):
    """The Gradium impls and a plain fake both satisfy the explicit protocols."""

    def test_gradium_stt_provider_and_session_conform(self) -> None:
        provider = GradiumStreamingSttProvider("key")
        session = GradiumStreamingSession(
            SimpleNamespace(), model_name="m", input_format="pcm_16000", language="fr"
        )
        self.assertIsInstance(provider, StreamingSttProvider)
        self.assertIsInstance(session, StreamingSttSession)

    def test_gradium_tts_provider_and_session_conform(self) -> None:
        provider = GradiumStreamingTtsProvider("key", voice_id="v")
        session = GradiumStreamingTtsSession(
            SimpleNamespace(), model_name="m", voice_id="v", output_format="pcm_16000"
        )
        self.assertIsInstance(provider, StreamingTtsProvider)
        self.assertIsInstance(session, StreamingTtsSession)

    def test_a_non_gradium_fake_also_conforms(self) -> None:
        # THEN a provider that never touches Gradium still satisfies the seam
        self.assertIsInstance(_FakeStreamingSttProvider(), StreamingSttProvider)
        self.assertIsInstance(_FakeStreamingTtsProvider(), StreamingTtsProvider)


class StreamingFactoryRegistryTest(unittest.TestCase):
    """The factory selects a streaming provider by name via a registry (not `== GRADIUM`)."""

    def tearDown(self) -> None:
        stt_factory._STREAMING_STT_BUILDERS.pop(FAKE_VENDOR, None)
        tts_factory._STREAMING_TTS_BUILDERS.pop(FAKE_VENDOR, None)

    def test_gradium_is_registered_and_fixture_is_batch_only(self) -> None:
        # GIVEN the shipped registry -> THEN gradium streams, fixture stays batch-only
        self.assertTrue(stt_factory.supports_streaming(stt_factory.GRADIUM))
        self.assertTrue(tts_factory.supports_streaming(tts_factory.GRADIUM))
        self.assertFalse(stt_factory.supports_streaming(stt_factory.FIXTURE))
        self.assertFalse(tts_factory.supports_streaming(tts_factory.FIXTURE))

    def test_build_streaming_raises_for_a_provider_without_a_variant(self) -> None:
        with self.assertRaises(ValueError):
            stt_factory.build_streaming_provider(stt_factory.FIXTURE)
        with self.assertRaises(ValueError):
            tts_factory.build_streaming_provider(tts_factory.FIXTURE)

    def test_registering_a_vendor_makes_it_selectable_by_name(self) -> None:
        # GIVEN a fake vendor registered at runtime (provider replaceability)
        stt_factory.register_streaming_provider(
            FAKE_VENDOR, lambda *, language=None: _FakeStreamingSttProvider(language=language)
        )
        tts_factory.register_streaming_provider(
            FAKE_VENDOR, lambda *, voice_id=None: _FakeStreamingTtsProvider(voice_id=voice_id)
        )
        # THEN it is reported as streaming-capable and built by name (no code branch)
        self.assertTrue(stt_factory.supports_streaming(FAKE_VENDOR))
        self.assertIn(FAKE_VENDOR, stt_factory.streaming_provider_names())
        stt = stt_factory.build_streaming_provider(FAKE_VENDOR, language="en")
        tts = tts_factory.build_streaming_provider(FAKE_VENDOR, voice_id="x")
        self.assertIsInstance(stt, StreamingSttProvider)
        self.assertIsInstance(tts, StreamingTtsProvider)
        self.assertEqual(stt.language, "en")
        self.assertEqual(tts.voice_id, "x")


class ServerStreamingSelectionTest(unittest.TestCase):
    """`server.py` picks the streaming provider from the registry, not a Gradium literal."""

    def setUp(self) -> None:
        stt_factory.register_streaming_provider(
            FAKE_VENDOR, lambda *, language=None: _FakeStreamingSttProvider(language=language)
        )
        tts_factory.register_streaming_provider(
            FAKE_VENDOR, lambda *, voice_id=None: _FakeStreamingTtsProvider(voice_id=voice_id)
        )

    def tearDown(self) -> None:
        stt_factory._STREAMING_STT_BUILDERS.pop(FAKE_VENDOR, None)
        tts_factory._STREAMING_TTS_BUILDERS.pop(FAKE_VENDOR, None)

    def test_a_registered_non_gradium_vendor_drives_the_webrtc_selection(self) -> None:
        from web_voice.server import _build_streaming_provider, _build_streaming_tts_provider

        args = SimpleNamespace(provider=FAKE_VENDOR, stt_mode="streaming", tts_mode="streaming")
        # THEN the fake vendor's streaming providers are selected without any Gradium branch
        self.assertIsInstance(_build_streaming_provider(args), StreamingSttProvider)
        self.assertIsInstance(_build_streaming_tts_provider(args), StreamingTtsProvider)

    def test_batch_only_or_batch_mode_falls_back_to_none(self) -> None:
        from web_voice.server import _build_streaming_provider, _build_streaming_tts_provider

        # GIVEN a provider with no streaming variant (fixture) -> batch fallback (None)
        fixture = SimpleNamespace(provider="fixture", stt_mode="streaming", tts_mode="streaming")
        self.assertIsNone(_build_streaming_provider(fixture))
        self.assertIsNone(_build_streaming_tts_provider(fixture))
        # AND an explicit batch mode also falls back, even for a streaming-capable vendor
        batch = SimpleNamespace(provider=FAKE_VENDOR, stt_mode="batch", tts_mode="batch")
        self.assertIsNone(_build_streaming_provider(batch))
        self.assertIsNone(_build_streaming_tts_provider(batch))


if __name__ == "__main__":
    unittest.main()
