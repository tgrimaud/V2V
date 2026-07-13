import base64
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tts_synthesis import (  # noqa: E402
    DEFAULT_VOICE_ID,
    EmptyTextError,
    GradiumTtsError,
    GradiumTtsProvider,
    build_provider,
)
from tts_synthesis.provider_factory import _resolve_voice_id  # noqa: E402

API_KEY = "super-secret-key-should-never-leak"


def _b64(pcm: bytes) -> str:
    return base64.b64encode(pcm).decode("ascii")


def _transport(messages: list[dict], captured: dict | None = None):
    def transport(url, headers, sent, timeout):
        if captured is not None:
            captured["url"] = url
            captured["headers"] = headers
            captured["sent"] = sent
        return messages

    return transport


def _provider(transport) -> GradiumTtsProvider:
    return GradiumTtsProvider(API_KEY, transport=transport)


class GradiumSynthesizeTest(unittest.TestCase):
    def test_audio_chunks_are_decoded_and_concatenated(self) -> None:
        # GIVEN a server stream of two audio chunks interleaved with a text echo
        messages = [
            {"type": "ready"},
            {"type": "audio", "audio": _b64(b"\x01\x02")},
            {"type": "text", "text": "ignored token echo"},
            {"type": "audio", "audio": _b64(b"\x03\x04")},
            {"type": "end_of_stream"},
        ]
        provider = _provider(_transport(messages))

        # WHEN the text is synthesized
        pcm = provider.synthesize("Bonjour")

        # THEN the base64 PCM chunks are decoded, concatenated, text echoes ignored
        self.assertEqual(pcm, b"\x01\x02\x03\x04")

    def test_stops_at_end_of_stream_ignoring_trailing_messages(self) -> None:
        # GIVEN audio after end_of_stream (must not be collected)
        messages = [
            {"type": "audio", "audio": _b64(b"\xaa")},
            {"type": "end_of_stream"},
            {"type": "audio", "audio": _b64(b"\xbb")},
        ]
        provider = _provider(_transport(messages))

        # WHEN synthesized
        pcm = provider.synthesize("hi")

        # THEN only audio before end_of_stream is returned
        self.assertEqual(pcm, b"\xaa")

    def test_setup_message_carries_voice_and_format_and_key_header(self) -> None:
        # GIVEN a captured transport
        captured: dict = {}
        provider = GradiumTtsProvider(
            API_KEY,
            voice_id="voice-xyz",
            output_format="pcm_16000",
            model_name="default",
            transport=_transport([{"type": "audio", "audio": _b64(b"\x01")}, {"type": "end_of_stream"}], captured),
        )

        # WHEN synthesized
        provider.synthesize("Bonjour le monde")

        # THEN the key travels only in the header and setup carries the negotiated params
        self.assertEqual(captured["headers"]["x-api-key"], API_KEY)
        setup = captured["sent"][0]
        self.assertEqual(setup["type"], "setup")
        self.assertEqual(setup["voice_id"], "voice-xyz")
        self.assertEqual(setup["output_format"], "pcm_16000")
        self.assertEqual(captured["sent"][1], {"type": "text", "text": "Bonjour le monde"})
        self.assertEqual(captured["sent"][2], {"type": "end_of_stream"})

    def test_empty_text_raises_empty_text_error_without_calling_transport(self) -> None:
        # GIVEN a transport that would fail if called
        def transport(url, headers, sent, timeout):
            raise AssertionError("transport must not be called for empty text")

        provider = _provider(transport)

        # WHEN synthesizing whitespace-only text
        # THEN it is signalled as UNAVAILABLE-class, not a provider failure
        with self.assertRaises(EmptyTextError):
            provider.synthesize("   ")

    def test_invalid_voice_error_is_reported_without_leaking_key(self) -> None:
        # GIVEN the server rejects the voice id
        messages = [{"type": "error", "code": 1011, "message": "Embeddings not found for bad-voice"}]
        provider = _provider(_transport(messages))

        # WHEN synthesized
        with self.assertRaises(GradiumTtsError) as ctx:
            provider.synthesize("Bonjour")

        # THEN the error is explicit and never contains the API key
        self.assertIn("voice id", str(ctx.exception).lower())
        self.assertNotIn(API_KEY, str(ctx.exception))

    def test_credit_exhaustion_is_reported(self) -> None:
        # GIVEN an error mentioning credits
        provider = _provider(_transport([{"type": "error", "message": "Insufficient credits remaining"}]))

        # WHEN synthesized
        with self.assertRaises(GradiumTtsError) as ctx:
            provider.synthesize("Bonjour")

        # THEN credit exhaustion is surfaced
        self.assertIn("credits", str(ctx.exception).lower())

    def test_auth_error_code_is_reported(self) -> None:
        # GIVEN a 401 error code
        provider = _provider(_transport([{"type": "error", "code": 401, "message": "denied"}]))

        # WHEN synthesized
        with self.assertRaises(GradiumTtsError) as ctx:
            provider.synthesize("Bonjour")

        # THEN authentication failure is surfaced without the key
        self.assertIn("authentication", str(ctx.exception).lower())
        self.assertNotIn(API_KEY, str(ctx.exception))

    def test_no_audio_produced_raises_error(self) -> None:
        # GIVEN a stream with no audio chunk at all
        provider = _provider(_transport([{"type": "ready"}, {"type": "end_of_stream"}]))

        # WHEN synthesized
        # THEN a provider failure is raised (no invented audio)
        with self.assertRaises(GradiumTtsError) as ctx:
            provider.synthesize("Bonjour")
        self.assertIn("no audio", str(ctx.exception).lower())

    def test_missing_api_key_is_rejected(self) -> None:
        # GIVEN no API key
        # WHEN a provider is constructed
        # THEN construction fails fast
        with self.assertRaises(ValueError):
            GradiumTtsProvider("")

    def test_missing_voice_id_is_rejected(self) -> None:
        # GIVEN an empty voice id
        # WHEN a provider is constructed
        # THEN construction fails fast
        with self.assertRaises(ValueError):
            GradiumTtsProvider(API_KEY, voice_id="")

    def test_audio_format_property_reflects_output_format(self) -> None:
        # GIVEN a provider with a chosen output format
        provider = GradiumTtsProvider(API_KEY, output_format="pcm_16000")
        # THEN it advertises that format for downstream WAV wrapping
        self.assertEqual(provider.audio_format, "pcm_16000")


class _FakeWebSocket:
    """Minimal async context manager standing in for a live websockets connection."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.sent: list[str] = []

    async def __aenter__(self) -> "_FakeWebSocket":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        if not self._replies:
            raise AssertionError("recv called with no remaining replies")
        return self._replies.pop(0)


def _fake_websockets_module(replies: list[str]) -> types.ModuleType:
    module = types.ModuleType("websockets")

    def connect(url, additional_headers=None):
        module.last_url = url
        module.last_headers = additional_headers
        return _FakeWebSocket(replies)

    module.connect = connect
    exceptions = types.ModuleType("websockets.exceptions")
    exceptions.WebSocketException = type("WebSocketException", (Exception,), {})
    module.exceptions = exceptions
    return module


class GradiumLiveTransportTest(unittest.TestCase):
    def test_default_transport_runs_the_real_asyncio_websocket_path(self) -> None:
        # GIVEN a fake websockets module (no injected transport) returning audio then end_of_stream
        replies = [
            json.dumps({"type": "audio", "audio": _b64(b"\x01\x02")}),
            json.dumps({"type": "end_of_stream"}),
        ]
        fake = _fake_websockets_module(replies)

        # WHEN synthesizing through the default _websocket_transport (asyncio.run path)
        with mock.patch.dict(sys.modules, {"websockets": fake, "websockets.exceptions": fake.exceptions}):
            provider = GradiumTtsProvider(API_KEY, voice_id="voice-xyz")
            pcm = provider.synthesize("Bonjour")

        # THEN the live path resolves end to end and the key travels only in the header
        self.assertEqual(pcm, b"\x01\x02")
        self.assertEqual(fake.last_headers, {"x-api-key": API_KEY})


class TtsProviderFactoryTest(unittest.TestCase):
    def test_fixture_provider_is_default(self) -> None:
        # GIVEN the default provider name
        provider = build_provider()
        # THEN the deterministic fixture provider is returned
        self.assertEqual(provider.name, "fixture-tts")

    def test_unknown_provider_is_rejected(self) -> None:
        # GIVEN an unsupported provider name
        with self.assertRaises(ValueError):
            build_provider("elevenlabs")

    def test_gradium_requires_api_key(self) -> None:
        # GIVEN no GRADIUM_API_KEY in the environment
        with mock.patch.dict("os.environ", {}, clear=True):
            # WHEN the gradium provider is built
            with self.assertRaises(ValueError):
                build_provider("gradium")

    def test_gradium_builds_with_key_and_defaults_voice(self) -> None:
        # GIVEN a key but the placeholder voice id
        with mock.patch.dict("os.environ", {"GRADIUM_API_KEY": API_KEY, "GRADIUM_VOICE_ID": "default"}, clear=True):
            provider = build_provider("gradium")
        # THEN a real Gradium provider is returned advertising the PCM format
        self.assertEqual(provider.name, "gradium-tts")
        self.assertEqual(provider.audio_format, "pcm_16000")

    def test_resolve_voice_id_normalizes_placeholder_and_empty(self) -> None:
        # GIVEN placeholder / empty / missing voice ids
        # THEN they resolve to the real default catalog voice
        self.assertEqual(_resolve_voice_id(None), DEFAULT_VOICE_ID)
        self.assertEqual(_resolve_voice_id(""), DEFAULT_VOICE_ID)
        self.assertEqual(_resolve_voice_id("  default "), DEFAULT_VOICE_ID)
        # AND a real voice id is preserved (trimmed)
        self.assertEqual(_resolve_voice_id("  voice-abc "), "voice-abc")


if __name__ == "__main__":
    unittest.main()
