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
from unittest import mock

from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation_backend import (  # noqa: E402
    DEGRADED_FALLBACK_TEXT,
    AnswerRequest,
    AnswerResult,
)
from tts_synthesis import FixtureTtsProvider  # noqa: E402
from web_voice import WebVoiceEgress, WebVoiceIngress  # noqa: E402
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

    async def test_responses_use_http_1_1(self) -> None:
        # BUG-012: behind the HAProxy h2 edge the backend must answer HTTP/1.1.
        client = await self._client()
        resp = await client.get("/")
        self.assertEqual((resp.version.major, resp.version.minor), (1, 1))

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

    async def test_run_blocking_propagates_correlation_context_into_executor(self) -> None:
        # GIVEN a correlation id bound in the caller's context (TASK-OBS-002)
        from web_voice.app import _run_blocking
        from voice_common.log_context import correlation_id_scope, get_correlation_id

        # WHEN a blocking call is off-loaded to the thread executor under that scope
        with correlation_id_scope("corr-batch"):
            seen = await _run_blocking(get_correlation_id)
        # THEN the worker thread inherited the id (run_in_executor does not copy it by default)
        self.assertEqual(seen, "corr-batch")

    async def test_turn_binds_the_correlation_id_for_the_processor_call(self) -> None:
        # GIVEN a processor that records the correlation id in scope when run_turn is invoked
        from types import SimpleNamespace
        from voice_common.log_context import get_correlation_id

        captured: dict[str, str | None] = {}

        class _CapturingProcessor:
            def run_turn(self, audio, envelope, telemetry, received_ms):  # noqa: ANN001
                captured["bound"] = get_correlation_id()
                captured["envelope"] = envelope.correlation_id
                return SimpleNamespace(transcript_result=None)

            def record_egress(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
                pass

        client = TestClient(TestServer(make_app(_CapturingProcessor())))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        # WHEN a turn is posted
        resp = await client.post(TURN_ROUTE, data=b"\x01\x02" * 100)
        # THEN the processor ran with the turn's correlation id bound (even in the executor)
        self.assertEqual(resp.status, 502)  # transcript None -> STT error path
        self.assertIsNotNone(captured["bound"])
        self.assertEqual(captured["bound"], captured["envelope"])

    async def test_turn_rejects_chunked_body_with_411(self) -> None:
        client = await self._client()
        resp = await client.post(TURN_ROUTE, data=_agen())
        self.assertEqual(resp.status, 411)
        self.assertEqual((await resp.json())["error"], "length_required")

    async def test_turn_over_cap_returns_json_413(self) -> None:
        # A body over the cap must return the SAME JSON 413 the stdlib handler did,
        # not aiohttp's default entity-too-large page (contract parity). Shrink the
        # cap so the test stays fast.
        import web_voice.app as app_module

        with mock.patch.object(app_module, "MAX_AUDIO_BYTES", 256):
            processor = build_turn_processor(PIPECAT, _ingress(), _egress())
            client = TestClient(TestServer(app_module.make_app(processor)))
            await client.start_server()
            self.addAsyncCleanup(client.close)
            resp = await client.post(TURN_ROUTE, data=b"\x00" * 4096)
        self.assertEqual(resp.status, 413)
        self.assertEqual((await resp.json())["error"], "audio_too_large")

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
        # Client-safe shape (RF-013): a generic message, never the raw provider reason
        # and never the internal `error_reason` field.
        self.assertTrue(body["message"])
        self.assertNotIn("error_reason", body)
        self.assertNotIn("provider unavailable", json.dumps(body))

    async def test_turn_audio_matches_across_runtimes(self) -> None:
        stdlib = await self._client(runtime=STDLIB)
        pipecat = await self._client(runtime=PIPECAT)
        r1 = await (await stdlib.post(TURN_ROUTE, data=b"\x03\x04" * 200)).json()
        r2 = await (await pipecat.post(TURN_ROUTE, data=b"\x03\x04" * 200)).json()
        self.assertEqual(r1["audio_base64"], r2["audio_base64"])

    async def test_both_runtimes_return_identical_client_safe_error_shape(self) -> None:
        # Migrated from the retired stdlib VoiceTurnEndpointTest (TASK-WEB-048 Phase 2):
        # the client-safe error contract must be identical across runtimes modulo the id.
        stdlib = await self._client(runtime=STDLIB, fail_stt=True)
        pipecat = await self._client(runtime=PIPECAT, fail_stt=True)
        b1 = await (await stdlib.post(TURN_ROUTE, data=b"\x01\x02" * 100)).json()
        b2 = await (await pipecat.post(TURN_ROUTE, data=b"\x01\x02" * 100)).json()
        b1.pop("correlation_id")
        b2.pop("correlation_id")
        self.assertEqual(b1, b2)

    async def test_turn_502_keeps_full_reason_in_server_log(self) -> None:
        # Migrated from the retired stdlib test: the raw provider reason must be absent
        # from the client body but present in the structured server-side turn log (RF-013).
        import io

        client = await self._client(fail_stt=True)
        captured = io.StringIO()
        original_stderr = sys.stderr
        sys.stderr = captured
        try:
            payload = await (await client.post(TURN_ROUTE, data=b"\x01\x02" * 100)).text()
        finally:
            sys.stderr = original_stderr
        self.assertNotIn("provider unavailable", payload)
        self.assertIn("provider unavailable", captured.getvalue())

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

    async def test_tts_empty_text_is_unavailable_json_502(self) -> None:
        # Migrated from the retired stdlib WebVoiceTtsServerTest (TASK-WEB-048 Phase 2):
        # whitespace/empty text invents no audio; it fails closed with a sanitized JSON 502.
        client = await self._client()
        resp = await client.post(f"{TTS_ROUTE}?text=")
        self.assertEqual(resp.status, 502)
        self.assertEqual(resp.headers["Content-Type"], "application/json")
        self.assertEqual((await resp.json())["outcome"], "unavailable")

    async def test_tts_provider_failure_is_client_safe_502(self) -> None:
        # Migrated from the retired stdlib test: a raising TTS provider yields a client-safe
        # 502 (stable code + correlation id + generic message, no raw reason leak — RF-013).
        class _RaisingTts:
            name = "boom-tts"
            audio_format = "pcm_16000"

            def synthesize(self, text: str) -> bytes:
                raise RuntimeError("Gradium TTS credits exhausted")

        processor = build_turn_processor(PIPECAT, _ingress(), WebVoiceEgress(_RaisingTts()))
        client = TestClient(TestServer(make_app(processor)))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        resp = await client.post(f"{TTS_ROUTE}?text=Bonjour&correlation_id=c9")
        self.assertEqual(resp.status, 502)
        body = await resp.json()
        self.assertEqual(body["error_code"], "tts_error")
        self.assertEqual(body["correlation_id"], "c9")
        self.assertTrue(body["message"])
        self.assertNotIn("error_reason", body)
        self.assertNotIn("credits exhausted", json.dumps(body))

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
