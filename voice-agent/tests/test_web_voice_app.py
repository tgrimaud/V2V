"""Parity tests for the single-port aiohttp app (TASK-WEB-038, ADR-0047).

Exercises `web_voice.app.make_app` through an aiohttp test client and asserts the
HTTP surface behaves byte-identically to the stdlib `ThreadingHTTPServer` handler:
static serving, favicon 204, OpenAPI, the `/api/voice/*` REST contracts (turn/stt/
tts happy + error paths), the chunked→411 guard, 404, and the WebRTC offer route.
"""

import base64
import json
import sys
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation_backend import (  # noqa: E402
    DEGRADED_FALLBACK_TEXT,
    AnswerOutcome,
    AnswerRequest,
    AnswerResult,
)
from tts_synthesis import FixtureTtsProvider  # noqa: E402
from web_voice import ChannelEnvelope, WebVoiceEgress, WebVoiceIngress  # noqa: E402
from web_voice.app import make_app  # noqa: E402
from web_voice.error_response import SessionCapacityError  # noqa: E402
from web_voice.runtime import PIPECAT, STDLIB, build_turn_processor  # noqa: E402
from web_voice.server import STT_ROUTE, TTS_ROUTE, TURN_ROUTE, WEBRTC_OFFER_ROUTE  # noqa: E402


class _StubStt:
    name = "stub-stt"

    def transcribe(self, audio_path) -> str:  # noqa: ANN001
        return "bonjour"


class _FailingStt:
    name = "failing-stt"

    def transcribe(self, audio_path) -> str:  # noqa: ANN001
        raise RuntimeError("provider unavailable")


class _UnavailableBackend:
    name = "unavailable-backend"

    def answer(self, request: AnswerRequest) -> AnswerResult:
        raise RuntimeError("backend endpoint unreachable")


def _ingress(fail: bool = False) -> WebVoiceIngress:
    return WebVoiceIngress(_FailingStt() if fail else _StubStt())


def _egress() -> WebVoiceEgress:
    return WebVoiceEgress(FixtureTtsProvider())


async def _agen():
    """Async body → aiohttp streams it with Transfer-Encoding: chunked (no Content-Length)."""
    yield b"\x01\x02" * 50


class WebVoiceAppTest(unittest.IsolatedAsyncioTestCase):
    async def _client(self, *, runtime=PIPECAT, fail_stt=False, backend=None, signaling=None) -> TestClient:
        processor = build_turn_processor(runtime, _ingress(fail_stt), _egress(), backend)
        client = TestClient(TestServer(make_app(processor, signaling)))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    # --- static + meta -------------------------------------------------------

    async def test_root_serves_index_html(self) -> None:
        client = await self._client()
        resp = await client.get("/")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(b"<", await resp.read())

    async def test_favicon_returns_204(self) -> None:
        client = await self._client()
        resp = await client.get("/favicon.ico")
        self.assertEqual(resp.status, 204)

    async def test_openapi_is_served_as_yaml(self) -> None:
        client = await self._client()
        resp = await client.get("/api/voice/openapi.yaml")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers["Content-Type"], "application/yaml; charset=utf-8")
        self.assertIn(b"openapi", await resp.read())

    async def test_unknown_static_path_is_404_json(self) -> None:
        client = await self._client()
        resp = await client.get("/does-not-exist.html")
        self.assertEqual(resp.status, 404)
        self.assertEqual((await resp.json())["error"], "not_found")

    async def test_static_path_traversal_is_rejected(self) -> None:
        client = await self._client()
        resp = await client.get("/../server.py")
        self.assertEqual(resp.status, 404)

    # --- /api/voice/turn -----------------------------------------------------

    async def test_turn_returns_json_with_base64_wav(self) -> None:
        client = await self._client()
        resp = await client.post(TURN_ROUTE, data=b"\x01\x02" * 200)
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers["Content-Type"], "application/json")
        data = await resp.json()
        wav = base64.b64decode(data["audio_base64"])
        self.assertEqual(wav[:4], b"RIFF")
        self.assertEqual(wav[8:12], b"WAVE")
        self.assertEqual(data["transcript"], "bonjour")
        self.assertNotEqual(data["answer"], data["transcript"])
        self.assertEqual(data["provider"], "stub-backend")
        self.assertTrue(data["correlation_id"])

    async def test_turn_rejects_chunked_body_with_411(self) -> None:
        client = await self._client()
        resp = await client.post(TURN_ROUTE, data=_agen())
        self.assertEqual(resp.status, 411)
        self.assertEqual((await resp.json())["error"], "length_required")

    async def test_turn_speaks_degraded_wav_when_backend_fails(self) -> None:
        client = await self._client(backend=_UnavailableBackend())
        resp = await client.post(TURN_ROUTE, data=b"\x01\x02" * 200)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(base64.b64decode(data["audio_base64"])[:4], b"RIFF")
        self.assertEqual(data["outcome"], "degraded")
        self.assertEqual(data["degraded_reason"], "backend_unavailable")
        self.assertEqual(data["answer"], DEGRADED_FALLBACK_TEXT)

    async def test_turn_fails_closed_with_client_safe_502_when_stt_fails(self) -> None:
        client = await self._client(fail_stt=True)
        resp = await client.post(TURN_ROUTE, data=b"\x01\x02" * 200)
        self.assertEqual(resp.status, 502)
        self.assertEqual(resp.headers["Content-Type"], "application/json")
        body = await resp.json()
        self.assertEqual(body["outcome"], "failed")
        self.assertTrue(body["error_code"])
        self.assertTrue(body["correlation_id"])
        self.assertNotIn("provider unavailable", json.dumps(body))

    async def test_turn_audio_matches_across_runtimes(self) -> None:
        stdlib = await self._client(runtime=STDLIB)
        pipecat = await self._client(runtime=PIPECAT)
        r1 = await (await stdlib.post(TURN_ROUTE, data=b"\x03\x04" * 200)).json()
        r2 = await (await pipecat.post(TURN_ROUTE, data=b"\x03\x04" * 200)).json()
        self.assertEqual(r1["audio_base64"], r2["audio_base64"])

    # --- /api/voice/stt + /tts ----------------------------------------------

    async def test_stt_returns_transcript_json(self) -> None:
        client = await self._client()
        resp = await client.post(STT_ROUTE, data=b"\x01\x02" * 200)
        self.assertEqual(resp.status, 200)
        self.assertEqual((await resp.json())["transcript"], "bonjour")

    async def test_stt_fails_closed_with_502(self) -> None:
        client = await self._client(fail_stt=True)
        resp = await client.post(STT_ROUTE, data=b"\x01\x02" * 200)
        self.assertEqual(resp.status, 502)
        self.assertNotIn("provider unavailable", json.dumps(await resp.json()))

    async def test_tts_returns_wav(self) -> None:
        client = await self._client()
        resp = await client.post(f"{TTS_ROUTE}?text=bonjour")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers["Content-Type"], "audio/wav")
        self.assertEqual((await resp.read())[:4], b"RIFF")

    # --- /api/voice/webrtc/offer --------------------------------------------

    async def test_offer_without_signaling_is_503_unavailable(self) -> None:
        client = await self._client()
        resp = await client.post(WEBRTC_OFFER_ROUTE, data=b"{}")
        self.assertEqual(resp.status, 503)
        self.assertEqual((await resp.json())["error"], "webrtc_unavailable")

    async def test_offer_capacity_returns_503_retry_after(self) -> None:
        class _FullSignaling:
            def handle_offer(self, offer, **kwargs):
                raise SessionCapacityError(8, 8)

        client = await self._client(signaling=_FullSignaling())
        resp = await client.post(WEBRTC_OFFER_ROUTE, data=b"{}")
        self.assertEqual(resp.status, 503)
        self.assertEqual(resp.headers["Retry-After"], "5")
        body = await resp.json()
        self.assertEqual(body["error"], "capacity")
        self.assertEqual(body["active"], 8)

    async def test_offer_other_error_stays_502_without_leaking_detail(self) -> None:
        class _BoomSignaling:
            def handle_offer(self, offer, **kwargs):
                raise RuntimeError("raw sdp negotiation boom")

        client = await self._client(signaling=_BoomSignaling())
        resp = await client.post(WEBRTC_OFFER_ROUTE, data=b"{}")
        self.assertEqual(resp.status, 502)
        payload = await resp.read()
        self.assertEqual(json.loads(payload)["error"], "webrtc_negotiation_failed")
        self.assertNotIn(b"boom", payload)


if __name__ == "__main__":
    unittest.main()
