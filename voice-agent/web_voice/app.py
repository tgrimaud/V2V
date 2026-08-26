"""Single-port aiohttp application for the web voice runtime (TASK-WEB-038, ADR-0047).

Serves, on ONE async server, everything the stdlib `ThreadingHTTPServer` served on
:8090 — static files, the OpenAPI spec, and the `/api/voice/*` REST endpoints — with
byte-identical contracts (paths, JSON shapes, HTTP/1.1, 204/404/411/413/502, the
path-traversal guard and the body cap). The live WebSocket audio path is mounted on
the same app in the next slice; until then the WS listener stays where it is.

The endpoint handlers delegate to the same transport-agnostic `VoiceTurnProcessor`
seam the stdlib handler used (`run_turn` / `transcribe_turn` / `synthesize_turn` /
`record_egress`). Those calls are blocking (a runtime may drive its own event loop),
so they run in a thread executor to keep the aiohttp event loop responsive — the
stdlib server got the same isolation for free via one thread per request.
"""

from __future__ import annotations

import functools
import json
from typing import Any, Callable

from aiohttp import web

from stt_validation.models import SttOutcome
from voice_common.telemetry import TelemetryRecorder, Timer

from .error_response import SessionCapacityError, client_error_body
from .server import (
    MAX_AUDIO_BYTES,
    MAX_TTS_TEXT_CHARS,
    OPENAPI_PATH,
    OPENAPI_ROUTE,
    STATIC_DIR,
    STT_ROUTE,
    TTS_ROUTE,
    TURN_ROUTE,
    WEBRTC_OFFER_ROUTE,
    _STATIC_TYPES,
    _envelope_from_query,
    _first,
    _full_turn_response,
    _log_turn,
    _turn_stt_error,
    _turn_success_body,
    _turn_tts_error,
)
from urllib.parse import parse_qs

_JSON = "application/json"


def _json_response(status: int, payload: dict, extra_headers: dict[str, str] | None = None) -> web.Response:
    """JSON reply matching the stdlib handler byte-for-byte (`application/json`, no charset)."""
    headers = {"Content-Type": _JSON}
    if extra_headers:
        headers.update(extra_headers)
    return web.Response(body=json.dumps(payload).encode("utf-8"), status=status, headers=headers)


def _is_chunked(request: web.Request) -> bool:
    return "chunked" in (request.headers.get("Transfer-Encoding", "") or "").lower()


async def _read_capped_body(request: web.Request) -> bytes | None:
    """Read the request body, enforcing the 25 MiB cap; None means over-cap (→ 413).

    Mirrors the stdlib `_read_body`: a declared Content-Length over the cap is rejected
    before reading, and the actual read is bounded so a lying/absent length cannot
    exceed the cap either.
    """
    declared = int(request.headers.get("Content-Length", "0") or "0")
    if declared > MAX_AUDIO_BYTES:
        return None
    try:
        body = await request.read()
    except web.HTTPRequestEntityTooLarge:
        # A body over aiohttp's client_max_size raises here; normalize it to the
        # same JSON 413 the stdlib handler returned instead of aiohttp's default page.
        return None
    if len(body) > MAX_AUDIO_BYTES:
        return None
    return body


async def _run_blocking(func: Callable, *args, **kwargs):
    """Off-load a blocking processor/signaling call to a thread so the loop stays free."""
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


def make_app(processor: Any, signaling: Any = None) -> web.Application:
    """Build the aiohttp application wiring the voice HTTP surface to `processor`.

    `signaling` (optional) is the WebRTC signaling service used by the offer route;
    when None the offer route answers 503 `webrtc_unavailable`, exactly as before.
    """
    app = web.Application(client_max_size=MAX_AUDIO_BYTES + 1024)

    async def handle_root(_request: web.Request) -> web.StreamResponse:
        return _serve_static("index.html")

    async def handle_favicon(_request: web.Request) -> web.StreamResponse:
        return web.Response(status=204)

    async def handle_openapi(_request: web.Request) -> web.StreamResponse:
        if not OPENAPI_PATH.is_file():
            return _json_response(404, {"error": "not_found"})
        return web.Response(
            body=OPENAPI_PATH.read_bytes(),
            headers={"Content-Type": "application/yaml; charset=utf-8"},
        )

    async def handle_static(request: web.Request) -> web.StreamResponse:
        return _serve_static(request.match_info.get("tail", ""))

    def _serve_static(filename: str) -> web.StreamResponse:
        target = (STATIC_DIR / filename).resolve()
        if STATIC_DIR not in target.parents or not target.is_file():
            return _json_response(404, {"error": "not_found"})
        return web.Response(
            body=target.read_bytes(),
            headers={"Content-Type": _STATIC_TYPES.get(target.suffix, "application/octet-stream")},
        )

    async def handle_stt(request: web.Request) -> web.StreamResponse:
        if _is_chunked(request):
            return _json_response(411, {"error": "length_required"})
        receive = Timer()
        audio = await _read_capped_body(request)
        received_ms = receive.elapsed_ms()
        if audio is None:
            return _json_response(413, {"error": "audio_too_large"})
        envelope = _envelope_from_query(request.query_string)
        telemetry = TelemetryRecorder()
        result = await _run_blocking(
            processor.transcribe_turn, audio, envelope, telemetry, received_ms=received_ms
        )
        _log_turn(telemetry)
        if result.outcome is SttOutcome.SUCCESS:
            return _json_response(200, result.to_dict())
        return _json_response(
            502, client_error_body(result.error_code, result.correlation_id, result.outcome.value)
        )

    async def handle_tts(request: web.Request) -> web.StreamResponse:
        text = _first(parse_qs(request.query_string), "text") or ""
        if len(text) > MAX_TTS_TEXT_CHARS:
            return _json_response(413, {"error": "text_too_large"})
        envelope = _envelope_from_query(request.query_string)
        telemetry = TelemetryRecorder()
        response = await _run_blocking(processor.synthesize_turn, text, envelope, telemetry)
        if response.wav is None:
            _log_turn(telemetry)
            result = response.result
            return _json_response(
                502, client_error_body(result.error_code, result.correlation_id, result.outcome.value)
            )
        send = Timer()
        reply = web.Response(body=response.wav, headers={"Content-Type": "audio/wav"})
        await _run_blocking(
            processor.record_egress, response, envelope, telemetry, sent_ms=send.elapsed_ms()
        )
        _log_turn(telemetry)
        return reply

    async def handle_turn(request: web.Request) -> web.StreamResponse:
        if _is_chunked(request):
            return _json_response(411, {"error": "length_required"})
        receive = Timer()
        audio = await _read_capped_body(request)
        received_ms = receive.elapsed_ms()
        if audio is None:
            return _json_response(413, {"error": "audio_too_large"})
        envelope = _envelope_from_query(request.query_string)
        telemetry = TelemetryRecorder()
        result = await _run_blocking(
            processor.run_turn, audio, envelope, telemetry, received_ms=received_ms
        )
        transcript = result.transcript_result
        if transcript is None or transcript.outcome is not SttOutcome.SUCCESS:
            _log_turn(telemetry)
            return _json_response(502, _turn_stt_error(transcript, envelope))
        response = result.tts_response
        if response is None or response.wav is None:
            _log_turn(telemetry)
            return _json_response(502, _turn_tts_error(response, envelope))
        full = _full_turn_response(result)
        send = Timer()
        reply = _json_response(200, _turn_success_body(transcript, result.answer_result, full.wav))
        await _run_blocking(
            processor.record_egress, full, envelope, telemetry, sent_ms=send.elapsed_ms()
        )
        _log_turn(telemetry)
        return reply

    async def handle_webrtc_offer(request: web.Request) -> web.StreamResponse:
        if _is_chunked(request):
            return _json_response(411, {"error": "length_required"})
        if signaling is None:
            return _json_response(503, {"error": "webrtc_unavailable"})
        body = await _read_capped_body(request)
        if body is None:
            return _json_response(413, {"error": "audio_too_large"})
        try:
            offer = json.loads(body or b"{}")
            answer = await _run_blocking(signaling.handle_offer, offer)
        except SessionCapacityError as exc:
            return _json_response(
                503,
                {"error": "capacity", "active": exc.active, "max": exc.cap},
                extra_headers={"Retry-After": "5"},
            )
        except Exception:  # noqa: BLE001 - never leak SDP/session detail to the client
            return _json_response(502, {"error": "webrtc_negotiation_failed"})
        return _json_response(200, answer)

    app.add_routes(
        [
            web.get("/", handle_root),
            web.get("/favicon.ico", handle_favicon),
            web.get(OPENAPI_ROUTE, handle_openapi),
            web.post(STT_ROUTE, handle_stt),
            web.post(TTS_ROUTE, handle_tts),
            web.post(TURN_ROUTE, handle_turn),
            web.post(WEBRTC_OFFER_ROUTE, handle_webrtc_offer),
            # Static catch-all LAST so it never shadows the explicit routes above.
            web.get("/{tail:.*}", handle_static),
        ]
    )
    return app
