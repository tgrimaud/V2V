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
import hmac
import json
from typing import Any, Callable

from aiohttp import web

from stt_validation.models import SttOutcome
from voice_common.telemetry import TelemetryRecorder, Timer

from .drain import (
    DRAIN_COMPLETED_EVENT,
    DRAIN_REMAINING_METRIC,
    DRAIN_REQUESTED_EVENT,
)
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
# Live WebSocket audio upgrade route (mounted only when a ws_handler is supplied, so
# importing this module stays free of the pipecat transport dependency).
WS_ROUTE = "/ws"
# Genesys Audio Connector AudioHook upgrade route (TASK-WEB-041), mounted only when a
# genesys_handler is supplied so the base HTTP surface stays unchanged otherwise.
GENESYS_ROUTE = "/genesys/audiohook"
# Graceful session-drain control route (TASK-OPS-010), mounted only when a drain_controller
# is supplied. Token-gated: an unconfigured token disables it (503) so the routed :8090 never
# exposes an unauthenticated "stop taking calls" trigger at the edge.
DRAIN_ROUTE = "/drain"


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


def _drain_timeout_ms(query_string: str, default_ms: int) -> int:
    """Resolve the drain wait budget: `?timeout_ms=` override, else the configured default."""
    raw = _first(parse_qs(query_string), "timeout_ms")
    if raw is None:
        return default_ms
    try:
        value = int(raw)
    except ValueError:
        return default_ms
    return value if value > 0 else default_ms


def _drain_token_matches(provided: str | None, expected: str) -> bool:
    """Constant-time compare of the drain token (avoid a timing side-channel on the header)."""
    return provided is not None and hmac.compare_digest(provided, expected)


async def _drain_and_report(controller: Any, timeout_ms: int):
    """Run the bounded drain, emitting the OTel drain-outcome evidence; returns the outcome."""
    telemetry = TelemetryRecorder()
    started = controller.active_sessions()
    telemetry.record(
        DRAIN_REQUESTED_EVENT, correlation_id="drain", active_sessions=started, timeout_ms=timeout_ms
    )
    outcome = await controller.wait_drained(timeout_ms)
    telemetry.record(
        DRAIN_COMPLETED_EVENT,
        correlation_id="drain",
        outcome=outcome.status,
        started_active=outcome.started_active,
        remaining=outcome.remaining,
        elapsed_ms=round(outcome.elapsed_ms, 1),
    )
    telemetry.metric(
        DRAIN_REMAINING_METRIC, float(outcome.remaining), correlation_id="drain", outcome=outcome.status
    )
    _log_turn(telemetry)
    return outcome


def _drain_body(outcome: Any, timeout_ms: int) -> dict:
    return {
        "status": outcome.status,
        "drained": outcome.drained,
        "active_at_start": outcome.started_active,
        "remaining": outcome.remaining,
        "elapsed_ms": round(outcome.elapsed_ms, 1),
        "timeout_ms": timeout_ms,
    }


def make_app(
    processor: Any,
    signaling: Any = None,
    ws_handler: Any = None,
    genesys_handler: Any = None,
    drain_controller: Any = None,
) -> web.Application:
    """Build the aiohttp application wiring the voice HTTP surface to `processor`.

    `signaling` (optional) is the WebRTC signaling service used by the offer route;
    when None the offer route answers 503 `webrtc_unavailable`, exactly as before.

    `ws_handler` (optional) is the live WebSocket audio handler (TASK-WEB-038 slice 2,
    `websocket_app.make_ws_handler`). When provided it is mounted at `GET /ws` on the
    same port; when None the `/ws` route is not registered (the interim `:8091` listener
    stays authoritative), so the HTTP surface is unchanged.

    `genesys_handler` (optional) is the Genesys Audio Connector handler (TASK-WEB-041,
    `genesys_app.make_genesys_handler`). When provided it is mounted at
    `GET /genesys/audiohook` on the same port; when None the route is not registered.
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

    async def handle_drain(request: web.Request) -> web.StreamResponse:
        # Fail-closed token gate: no token configured => the drain trigger is disabled, so the
        # edge-facing :8090 never exposes an unauthenticated "stop taking calls" control.
        token = drain_controller.token
        if token is None:
            return _json_response(503, {"error": "drain_not_configured"})
        if not _drain_token_matches(request.headers.get("X-Drain-Token"), token):
            return _json_response(403, {"error": "forbidden"})
        timeout_ms = _drain_timeout_ms(request.query_string, drain_controller.default_timeout_ms)
        outcome = await _drain_and_report(drain_controller, timeout_ms)
        return _json_response(200, _drain_body(outcome, timeout_ms))

    routes = [
        web.get("/", handle_root),
        web.get("/favicon.ico", handle_favicon),
        web.get(OPENAPI_ROUTE, handle_openapi),
        web.post(STT_ROUTE, handle_stt),
        web.post(TTS_ROUTE, handle_tts),
        web.post(TURN_ROUTE, handle_turn),
        web.post(WEBRTC_OFFER_ROUTE, handle_webrtc_offer),
    ]
    if ws_handler is not None:
        # Registered before the static catch-all so the upgrade route wins over it.
        routes.append(web.get(WS_ROUTE, ws_handler))
    if genesys_handler is not None:
        routes.append(web.get(GENESYS_ROUTE, genesys_handler))
    if drain_controller is not None:
        routes.append(web.post(DRAIN_ROUTE, handle_drain))
    # Static catch-all LAST so it never shadows the explicit routes above.
    routes.append(web.get("/{tail:.*}", handle_static))
    app.add_routes(routes)
    return app
