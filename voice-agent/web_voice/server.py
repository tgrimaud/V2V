"""Minimal web voice runtime server (TASK-WEB-001, TASK-WEB-005).

Serves the mic-capture page and exposes the voice endpoints:
- `POST /api/voice/stt`  PCM16 mono 16 kHz audio in -> transcript JSON out.
- `POST /api/voice/tts`  `?text=` in -> WAV audio out.
- `POST /api/voice/turn` PCM16 audio in -> full STT -> backend answer -> TTS loop ->
  JSON out: transcript + answer text + answer audio as base64 WAV (Decision #9).

The runtime is selected at startup (`--runtime {stdlib,pipecat}`, env `VOICE_RUNTIME`):
the server drives a `VoiceTurnProcessor` seam, so the stdlib and Pipecat runtimes
coexist and produce identical output. The STT/TTS provider is selected with
`--provider`, defaulting to Gradium with a fixture fallback for offline development.
"""

import argparse
import base64
import json
import os
import socketserver
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation_backend import BACKEND_NAMES, STUB, build_backend  # noqa: E402
from stt_validation.models import SttOutcome  # noqa: E402
from stt_validation.provider_factory import (  # noqa: E402
    GRADIUM,
    PROVIDER_NAMES,
    build_provider,
    build_streaming_provider,
    supports_streaming as stt_supports_streaming,
)
from tts_synthesis.provider_factory import (  # noqa: E402
    build_provider as build_tts_provider,
    build_streaming_provider as build_streaming_tts_provider,
    supports_streaming as tts_supports_streaming,
)
from voice_common.otel_export import export_recorder  # noqa: E402
from voice_common.telemetry import TelemetryRecorder, Timer  # noqa: E402

from .egress import VoiceResponse, WebVoiceEgress, pcm_to_wav  # noqa: E402
from .egress import _sample_rate_from_format  # noqa: E402
from .envelope import ChannelEnvelope  # noqa: E402
from .error_response import SessionCapacityError, client_error_body  # noqa: E402
from .ingress import WebVoiceIngress  # noqa: E402
from .runtime import (  # noqa: E402
    DEFAULT_RUNTIME,
    RUNTIME_NAMES,
    VoiceTurnProcessor,
    build_turn_processor,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
OPENAPI_PATH = Path(__file__).resolve().parent / "openapi.yaml"
STT_ROUTE = "/api/voice/stt"
TTS_ROUTE = "/api/voice/tts"
TURN_ROUTE = "/api/voice/turn"
WEBRTC_OFFER_ROUTE = "/api/voice/webrtc/offer"
OPENAPI_ROUTE = "/api/voice/openapi.yaml"
RUNTIME_ENV_VAR = "VOICE_RUNTIME"
BACKEND_ENV_VAR = "VOICE_BACKEND"
WEBRTC_ENV_VAR = "VOICE_WEBRTC"
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # guard against oversized uploads (~13 min PCM16 16k)
MAX_TTS_TEXT_CHARS = 5000  # guard against oversized synthesis requests
_STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8"}


class WebVoiceHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server that skips the reverse-DNS FQDN lookup on bind.

    `HTTPServer.server_bind()` calls `socket.getfqdn()`, which can block for tens
    of seconds when reverse DNS is slow or misconfigured. A local ingress server
    does not need the FQDN, so we replicate the bind without that call.
    """

    daemon_threads = True

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


def build_handler(
    processor: VoiceTurnProcessor, signaling: Any = None
) -> type[BaseHTTPRequestHandler]:
    class WebVoiceHandler(BaseHTTPRequestHandler):
        # Answer in HTTP/1.1 (the BaseHTTPRequestHandler default is HTTP/1.0). Behind the
        # HAProxy TLS edge (alpn h2,http/1.1) a browser negotiates HTTP/2; HAProxy cannot
        # mux an HTTP/1.0 backend response onto an h2 client and returns "Empty reply"
        # (BUG-012). Every bodied response here sets Content-Length and the only bodiless
        # response is 204, so HTTP/1.1 keep-alive has definite framing on all paths.
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlparse(self.path).path
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if path == OPENAPI_ROUTE:
                self._serve_openapi()
                return
            filename = "index.html" if path in ("/", "") else path.lstrip("/")
            self._serve_static(filename)

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlparse(self.path).path
            if path in (STT_ROUTE, TURN_ROUTE, WEBRTC_OFFER_ROUTE) and self._is_chunked():
                # Bodies are sized and capped via Content-Length; a chunked body has none, so
                # _read_body would read it as empty (length 0) and it would look like an empty
                # turn. Ask the client to send a Content-Length instead of failing silently (411).
                self._send_json(411, {"error": "length_required"})
                return
            if path == STT_ROUTE:
                self._handle_stt()
            elif path == TTS_ROUTE:
                self._handle_tts()
            elif path == TURN_ROUTE:
                self._handle_turn()
            elif path == WEBRTC_OFFER_ROUTE:
                self._handle_webrtc_offer()
            else:
                self._send_json(404, {"error": "not_found"})

        def _handle_webrtc_offer(self) -> None:
            if signaling is None:
                self._send_json(503, {"error": "webrtc_unavailable"})
                return
            body = self._read_body()
            if body is None:
                self._send_json(413, {"error": "audio_too_large"})
                return
            try:
                offer = json.loads(body or b"{}")
                answer = signaling.handle_offer(offer)
            except SessionCapacityError as exc:
                # Backpressure (TASK-WEB-024): the concurrency ceiling is reached. 503 +
                # Retry-After tells the client to retry later instead of failing hard; the
                # refusal is already recorded in the signaling telemetry (no detail leaked).
                self._send_json(
                    503,
                    {"error": "capacity", "active": exc.active, "max": exc.cap},
                    extra_headers={"Retry-After": "5"},
                )
                return
            except Exception:  # noqa: BLE001 - never leak SDP/session detail to the client
                self._send_json(502, {"error": "webrtc_negotiation_failed"})
                return
            self._send_json(200, answer)

        def _handle_stt(self) -> None:
            receive = Timer()
            audio = self._read_body()
            received_ms = receive.elapsed_ms()
            if audio is None:
                self._send_json(413, {"error": "audio_too_large"})
                return
            envelope = _envelope_from_query(urlparse(self.path).query)
            telemetry = TelemetryRecorder()
            result = processor.transcribe_turn(audio, envelope, telemetry, received_ms=received_ms)
            _log_turn(telemetry)
            if result.outcome is SttOutcome.SUCCESS:
                self._send_json(200, result.to_dict())
                return
            # Client-safe body: stable code + correlation id, never the raw provider
            # reason (RF-013). Full reason stays in the telemetry logged above.
            self._send_json(
                502,
                client_error_body(result.error_code, result.correlation_id, result.outcome.value),
            )

        def _handle_tts(self) -> None:
            query = urlparse(self.path).query
            text = _first(parse_qs(query), "text") or ""
            if len(text) > MAX_TTS_TEXT_CHARS:
                self._send_json(413, {"error": "text_too_large"})
                return
            envelope = _envelope_from_query(query)
            telemetry = TelemetryRecorder()
            response = processor.synthesize_turn(text, envelope, telemetry)
            if response.wav is None:
                _log_turn(telemetry)
                result = response.result
                self._send_json(
                    502,
                    client_error_body(result.error_code, result.correlation_id, result.outcome.value),
                )
                return
            send = Timer()
            self._send_wav(response.wav)
            processor.record_egress(response, envelope, telemetry, sent_ms=send.elapsed_ms())
            _log_turn(telemetry)

        def _handle_turn(self) -> None:
            receive = Timer()
            audio = self._read_body()
            received_ms = receive.elapsed_ms()
            if audio is None:
                self._send_json(413, {"error": "audio_too_large"})
                return
            envelope = _envelope_from_query(urlparse(self.path).query)
            telemetry = TelemetryRecorder()
            result = processor.run_turn(audio, envelope, telemetry, received_ms=received_ms)
            transcript = result.transcript_result
            if transcript is None or transcript.outcome is not SttOutcome.SUCCESS:
                _log_turn(telemetry)
                self._send_json(502, _turn_stt_error(transcript, envelope))
                return
            response = result.tts_response
            if response is None or response.wav is None:
                _log_turn(telemetry)
                self._send_json(502, _turn_tts_error(response, envelope))
                return
            # Send EVERY synthesized sentence, not just the last (BUG-015). With backend
            # streaming on (default), the answer arrives as one TextFrame per sentence, so
            # `tts_response` holds only the last synthesis while `result.audio` is the whole
            # answer accumulated by the capture sink; build one WAV from the accumulated PCM.
            full = _full_turn_response(result)
            send = Timer()
            self._send_json(200, _turn_success_body(transcript, result.answer_result, full.wav))
            processor.record_egress(full, envelope, telemetry, sent_ms=send.elapsed_ms())
            _log_turn(telemetry)

        def _is_chunked(self) -> bool:
            return "chunked" in (self.headers.get("Transfer-Encoding", "") or "").lower()

        def _read_body(self) -> bytes | None:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length > MAX_AUDIO_BYTES:
                return None
            return self.rfile.read(length) if length else b""

        def _serve_openapi(self) -> None:
            # Serve the hand-written OpenAPI spec (TASK-WEB-016). Committed alongside the
            # code and mirrors docs/architecture/voice-runtime-http-contract.md.
            if not OPENAPI_PATH.is_file():
                self._send_json(404, {"error": "not_found"})
                return
            body = OPENAPI_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/yaml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self, filename: str) -> None:
            target = (STATIC_DIR / filename).resolve()
            if STATIC_DIR not in target.parents or not target.is_file():
                self._send_json(404, {"error": "not_found"})
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", _STATIC_TYPES.get(target.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(
            self, status: int, payload: dict, extra_headers: dict[str, str] | None = None
        ) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_wav(self, wav: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            self.end_headers()
            self.wfile.write(wav)

        def log_message(self, *_args) -> None:  # silence default per-request stderr noise
            return

    return WebVoiceHandler


def _turn_stt_error(transcript, envelope) -> dict[str, Any]:
    """Client-safe 502 body for a `/turn` that failed at the STT slice (RF-013)."""
    if transcript is None:
        return client_error_body("no_transcript", envelope.correlation_id)
    return client_error_body(transcript.error_code, transcript.correlation_id, transcript.outcome.value)


def _full_turn_response(result) -> VoiceResponse:
    """Wrap the whole-answer PCM accumulated at the capture sink into one WAV (BUG-015).

    `result.tts_response` is the last synthesized sentence only (the batch TTS processor
    overwrites it per `TextFrame`), while `result.audio` is every sentence in order. Send
    the full audio; if nothing was accumulated (no sink frame), fall back to the last
    synthesis so behaviour never regresses on the single-sentence / non-streaming path.
    """
    last = result.tts_response
    if not result.audio:
        return last
    sample_rate = _sample_rate_from_format(last.result.audio_format)
    return VoiceResponse(result=last.result, wav=pcm_to_wav(result.audio, sample_rate))


def _turn_tts_error(response, envelope) -> dict[str, Any]:
    """Client-safe 502 body for a `/turn` that produced no audio answer (RF-013)."""
    if response is None:
        return client_error_body("no_audio", envelope.correlation_id)
    result = response.result
    return client_error_body(result.error_code, result.correlation_id, result.outcome.value)


def _turn_success_body(transcript, answer, wav: bytes) -> dict[str, Any]:
    """Single JSON `/turn` success reply (Decision #9): audio as base64 with its metadata.

    Replaces the previous `audio/wav` body + `X-Voice-*` / `X-Answer-*` headers. The transcript
    and spoken answer are unbounded, accented customer text; percent-encoded into headers they
    could exceed proxy header-size limits on long answers (truncation / 502) and leak into proxy
    access logs. A JSON body has no such size cap, keeps the reply shape uniform with the 502
    error body, and — since `/turn` already returns the whole WAV at once (streaming is the
    WebRTC path) — base64 buffering is a non-issue here. `degraded_reason` stays a stable,
    non-sensitive code (e.g. `backend_unavailable`) so the client/QA still see why a safe
    fallback was spoken (TASK-WEB-003-F).
    """
    body: dict[str, Any] = {
        "correlation_id": transcript.correlation_id,
        "transcript": transcript.transcript,
        "audio_base64": base64.b64encode(wav).decode("ascii"),
        "audio_format": "wav",
    }
    if answer is not None:
        body["answer"] = answer.text
        body["provider"] = answer.provider
        body["outcome"] = answer.outcome.value
        if answer.degraded_reason:
            body["degraded_reason"] = answer.degraded_reason
    return body


def _envelope_from_query(query: str) -> ChannelEnvelope:
    params = parse_qs(query)
    return ChannelEnvelope.for_web_turn(
        conversation_id=_first(params, "conversation_id"),
        external_session_id=_first(params, "session_id"),
        correlation_id=_first(params, "correlation_id"),
        language=_first(params, "language"),
    )


def _first(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    return values[0] if values else None


def _log_turn(telemetry: TelemetryRecorder) -> None:
    payload = {
        "spans": [span.__dict__ for span in telemetry.spans()],
        "events": [event.__dict__ for event in telemetry.events()],
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    # Additive OTLP export (TASK-OBS-001): no-op unless OTEL export env is set; never raises.
    export_recorder(telemetry)


def build_ice_servers(
    stun: str = "",
    turn: str = "",
    turn_username: str = "",
    turn_credential: str = "",
) -> list:
    """Build the WebRTC ICE server list from env-provided STUN/TURN config.

    STUN needs only URLs; TURN additionally needs credentials for relayed media.
    `SmallWebRTCConnection` requires a *homogeneous* list (all `str` OR all
    `IceServer`), so when any TURN server is configured every entry — STUN
    included — is promoted to an `IceServer`; with STUN only we keep the plain
    `list[str]` form (unchanged behaviour). A TURN URL without credentials is a
    misconfiguration (a relay won't authenticate), so it is dropped with no
    silent fallback that would look like it works.
    """
    stun_urls = [s.strip() for s in stun.split(",") if s.strip()]
    turn_urls = [t.strip() for t in turn.split(",") if t.strip()]
    if not turn_urls:
        return stun_urls
    from pipecat.transports.smallwebrtc.connection import IceServer

    servers: list = [IceServer(urls=url) for url in stun_urls]
    if turn_username and turn_credential:
        servers.extend(
            IceServer(urls=url, username=turn_username, credential=turn_credential)
            for url in turn_urls
        )
    else:
        print(
            "[voice] VOICE_TURN set without VOICE_TURN_USERNAME/CREDENTIAL; "
            "TURN relays ignored (a relay cannot authenticate without credentials)",
            file=sys.stderr,
        )
    return servers


def _build_signaling(args, ingress, egress, backend) -> tuple[Any, Any]:
    """Build the WebRTC signaling service + its background loop, or (None, None).

    `--webrtc off` disables it; `auto` (default) enables it only when the extra is
    importable; `on` requires it. Returns (signaling, loop) so main() can shut down.
    """
    if args.webrtc == "off":
        return None, None
    from .webrtc_support import probe_webrtc_support

    if not probe_webrtc_support().available:
        if args.webrtc == "on":
            raise SystemExit('WebRTC requested but unavailable: pip install "pipecat-ai[webrtc]"')
        return None, None
    from .async_loop import BackgroundEventLoop
    from .webrtc_signaling import WebRtcSignalingService

    loop = BackgroundEventLoop()
    loop.start()
    ice = build_ice_servers(
        stun=args.stun or "",
        turn=getattr(args, "turn", "") or "",
        turn_username=getattr(args, "turn_username", "") or "",
        turn_credential=getattr(args, "turn_credential", "") or "",
    )
    signaling = WebRtcSignalingService(
        ingress=ingress,
        egress=egress,
        backend=backend,
        loop=loop,
        ice_servers=ice,
        streaming_provider=_build_streaming_provider(args),
        streaming_tts_provider=_build_streaming_tts_provider(args),
        streaming_providers_by_language=_streaming_stt_by_language(args),
        streaming_tts_providers_by_language=_streaming_tts_by_language(args),
    )
    return signaling, loop


def _build_ws_signaling(args, ingress, egress, backend, loop) -> tuple[Any, Any]:
    """Build the interim browser WebSocket signaling (TASK-WEB-028), or (None, None).

    Reuses the WebRTC background loop when present; otherwise starts its own so the WS
    path works even with `--webrtc off`. `--websocket off` disables it; `auto` (default)
    enables it only when the websockets transport is importable; `on` requires it. The
    session is transport-agnostic — the same `SessionFactory` as WebRTC is used, only the
    transport differs (ADR-0043, TASK-WEB-027). Returns (ws_signaling, owned_loop) so
    main() stops the loop only when this builder created it.
    """
    if getattr(args, "websocket", "auto") == "off":
        return None, None
    from .websocket_support import probe_websocket_support

    if not probe_websocket_support().available:
        if args.websocket == "on":
            raise SystemExit('WebSocket requested but unavailable: pip install "websockets>=13,<17"')
        return None, None
    from .async_loop import BackgroundEventLoop
    from .websocket_signaling import (
        WebSocketSignalingService,
        ws_host_config,
        ws_language_config,
        ws_max_sessions_config,
        ws_port_config,
    )

    owned_loop = None
    if loop is None:
        loop = BackgroundEventLoop()
        loop.start()
        owned_loop = loop
    ws_signaling = WebSocketSignalingService(
        factory=_build_ws_session_factory(args, ingress, egress, backend),
        loop=loop,
        host=ws_host_config(),
        port=ws_port_config(),
        default_language=ws_language_config(),
        max_sessions=ws_max_sessions_config(),
    )
    ws_signaling.start()
    return ws_signaling, owned_loop


def _build_ws_session_factory(args, ingress, egress, backend, transport_label="websocket"):
    """Build the transport-agnostic `SessionFactory` shared by the WS + Genesys transports.

    The interim `SingleClientWebsocketServerTransport` (`:8091`), the aiohttp-native
    `/ws` transport (single port, ADR-0047) and the Genesys Audio Connector adapter
    (TASK-WEB-041) differ only in the transport they pass to `build_session`; the session
    core is identical (ADR-0043, TASK-WEB-027). `transport_label` is stamped on the
    channel-egress span so a per-slice report can split `websocket` from `genesys`.
    """
    from .session_factory import SessionFactory

    return SessionFactory(
        ingress=ingress,
        egress=egress,
        backend=backend,
        streaming_provider=_build_streaming_provider(args),
        streaming_tts_provider=_build_streaming_tts_provider(args),
        streaming_providers_by_language=_streaming_stt_by_language(args),
        streaming_tts_providers_by_language=_streaming_tts_by_language(args),
        transport_label=transport_label,
    )


def _build_genesys_handler(args, ingress, egress, backend):
    """Build the aiohttp `/genesys/audiohook` handler for the single-port path, or None.

    Rides aiohttp's own `WebSocketResponse` (no extra package), reusing the shared
    `SessionFactory` (transport label `genesys`) exactly like `/ws`. `--genesys off`
    disables it; `auto` (default) / `on` enable it. Concurrency, codec and the graceful
    15-minute cap are env-tunable (TASK-WEB-041 / ADR-0049).
    """
    if getattr(args, "genesys", "auto") == "off":
        return None
    from .genesys_app import (
        genesys_codec_config,
        genesys_max_session_s_config,
        genesys_max_sessions_config,
        make_genesys_handler,
    )
    from .websocket_signaling import ws_language_config

    return make_genesys_handler(
        _build_ws_session_factory(args, ingress, egress, backend, transport_label="genesys"),
        default_language=ws_language_config(),
        max_sessions=genesys_max_sessions_config(),
        wire_codec=genesys_codec_config(),
        max_session_s=genesys_max_session_s_config(),
    )


def _build_ws_handler(args, ingress, egress, backend):
    """Build the aiohttp-native `/ws` handler for the single-port path, or None.

    Unlike the interim `:8091` listener this needs **no `websockets` package** — it rides
    aiohttp's own `WebSocketResponse` — so availability is gated only by `--websocket`
    (`off` disables it; `auto`/`on` enable it). Concurrency is lifted from the interim
    one-call cap to `VOICE_MAX_WS_SESSIONS` (ADR-0047).
    """
    if getattr(args, "websocket", "auto") == "off":
        return None
    from .websocket_app import make_ws_handler, ws_async_max_sessions_config
    from .websocket_signaling import ws_language_config

    return make_ws_handler(
        _build_ws_session_factory(args, ingress, egress, backend),
        default_language=ws_language_config(),
        max_sessions=ws_async_max_sessions_config(),
    )


def _streaming_stt_by_language(args) -> dict[str, Any]:
    """Per-session streaming STT providers keyed by language (US-042, WebRTC path)."""
    if args.stt_mode != "streaming" or not stt_supports_streaming(args.provider):
        return {}
    return {
        "fr": build_streaming_provider(args.provider, language="fr"),
        "en": build_streaming_provider(args.provider, language="en"),
    }


def _streaming_tts_by_language(args) -> dict[str, Any]:
    """Per-session streaming TTS voices keyed by language (US-042, WebRTC path). French uses the
    default voice; English uses GRADIUM_VOICE_ID_EN when configured (Gradium picks language by voice).
    """
    if args.tts_mode != "streaming" or not tts_supports_streaming(args.provider):
        return {}
    by_language = {"fr": build_streaming_tts_provider(args.provider)}
    english_voice = os.environ.get("GRADIUM_VOICE_ID_EN")
    if english_voice:
        by_language["en"] = build_streaming_tts_provider(args.provider, voice_id=english_voice)
    return by_language


def _stt_by_language(provider_name: str) -> dict[str, Any]:
    """Per-session STT providers keyed by language (US-042). Gradium listens in the selected
    language; the fixture provider is language-agnostic so the map stays empty (single provider).
    """
    if provider_name != GRADIUM:
        return {}
    return {"fr": build_provider(provider_name, language="fr"), "en": build_provider(provider_name, language="en")}


def _tts_by_language(provider_name: str) -> dict[str, Any]:
    """Per-session TTS voices keyed by language (US-042). Gradium speaks the language of the voice,
    so French uses the default voice and English uses GRADIUM_VOICE_ID_EN when configured.
    """
    if provider_name != GRADIUM:
        return {}
    by_language = {"fr": build_tts_provider(provider_name)}
    english_voice = os.environ.get("GRADIUM_VOICE_ID_EN")
    if english_voice:
        by_language["en"] = build_tts_provider(provider_name, voice_id=english_voice)
    return by_language


def _build_streaming_provider(args) -> Any:
    """Build the streaming STT provider for the WebRTC path, or None (batch fallback).

    Selection is keyed on the provider registry (TASK-WEB-023): a provider with no
    registered streaming variant, or an explicit `--stt-mode batch`, keeps the batch
    utterance-aggregator path. Adding a vendor is a registration, not an edit here.
    """
    if args.stt_mode != "streaming" or not stt_supports_streaming(args.provider):
        return None
    return build_streaming_provider(args.provider)


def _build_streaming_tts_provider(args) -> Any:
    """Build the streaming TTS provider for the WebRTC path, or None (batch fallback).

    Selection is keyed on the provider registry (TASK-WEB-023): a provider with no
    registered streaming variant, or an explicit `--tts-mode batch`, keeps the batch
    TTS processor (synthesize whole clip then play). Adding a vendor is a registration.
    """
    if args.tts_mode != "streaming" or not tts_supports_streaming(args.provider):
        return None
    return build_streaming_tts_provider(args.provider)


def main() -> int:
    args = _parse_args()
    ingress = WebVoiceIngress(
        build_provider(args.provider), providers_by_language=_stt_by_language(args.provider)
    )
    egress = WebVoiceEgress(
        build_tts_provider(args.provider), providers_by_language=_tts_by_language(args.provider)
    )
    # `stub` (default) is the deterministic offline answer; `http` targets a real
    # conversation endpoint configured via VOICE_BACKEND_URL (TASK-WEB-003-C).
    backend = build_backend(args.backend)
    processor = build_turn_processor(args.runtime, ingress, egress, backend)
    signaling, loop = _build_signaling(args, ingress, egress, backend)
    # ADR-0047: on the aiohttp path the live WS rides the SAME port (`/ws`) via an
    # aiohttp-native transport, so the interim single-client `:8091` listener is NOT
    # started; the stdlib path keeps that listener unchanged.
    genesys_handler = None
    if args.server == "aiohttp":
        ws_handler = _build_ws_handler(args, ingress, egress, backend)
        genesys_handler = _build_genesys_handler(args, ingress, egress, backend)
        ws_signaling, ws_loop = None, None
        ws_status = f"on:{args.port}/ws" if ws_handler else "off"
    else:
        ws_handler = None
        ws_signaling, ws_loop = _build_ws_signaling(args, ingress, egress, backend, loop)
        ws_status = f"on:{ws_signaling.port}" if ws_signaling else "off"
    genesys_status = f"on:{args.port}/genesys/audiohook" if genesys_handler else "off"
    print(
        f"Web voice server on http://{args.host}:{args.port} "
        f"(server={args.server}, provider={args.provider}, runtime={args.runtime}, "
        f"backend={backend.name}, webrtc={'on' if signaling else 'off'}, websocket={ws_status}, "
        f"genesys={genesys_status}, stt_mode={args.stt_mode}, tts_mode={args.tts_mode})",
        file=sys.stderr,
    )
    try:
        _serve(args, processor, signaling, ws_handler, genesys_handler)
    finally:
        if ws_signaling is not None:
            ws_signaling.close()
        if signaling is not None:
            signaling.close()
        if loop is not None:
            loop.stop()
        if ws_loop is not None:
            ws_loop.stop()
        # Stop the batch pipecat processor's background loop if it started one (TASK-WEB-024).
        close = getattr(processor, "close", None)
        if callable(close):
            close()
    return 0


def _serve(
    args,
    processor: VoiceTurnProcessor,
    signaling: Any,
    ws_handler: Any = None,
    genesys_handler: Any = None,
) -> None:
    """Run the selected HTTP server (blocking until shutdown).

    `aiohttp` (TASK-WEB-038 / ADR-0047) is the single-async-server target: static, REST,
    the live WebSocket audio path and — when `genesys_handler` is supplied — the Genesys
    Audio Connector `wss` endpoint all ride one port.
    `stdlib` is the historical `ThreadingHTTPServer` (HTTP only; WS stays on `:8091`).
    """
    if args.server == "aiohttp":
        from aiohttp import web

        from .app import make_app

        # access_log=None: the stdlib handler silenced per-request logging (log_message
        # no-op); aiohttp's default access format logs "%r" (the request line WITH the
        # query string, which carries conversation_id/correlation_id/session_id/language).
        # Keep those opaque IDs out of the access log — telemetry already records them.
        web.run_app(
            make_app(processor, signaling, ws_handler=ws_handler, genesys_handler=genesys_handler),
            host=args.host,
            port=args.port,
            print=None,
            access_log=None,
        )
        return
    server = WebVoiceHTTPServer((args.host, args.port), build_handler(processor, signaling))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the web voice runtime server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument(
        "--server",
        choices=("stdlib", "aiohttp"),
        default=os.environ.get("VOICE_SERVER", "aiohttp"),
        help="HTTP server: 'aiohttp' (default, single async HTTP+WS server on one port, "
        "TASK-WEB-038/ADR-0047) or 'stdlib' (legacy ThreadingHTTPServer + interim :8091 WS)",
    )
    parser.add_argument("--provider", choices=PROVIDER_NAMES, default=GRADIUM)
    parser.add_argument(
        "--runtime",
        choices=RUNTIME_NAMES,
        default=os.environ.get(RUNTIME_ENV_VAR, DEFAULT_RUNTIME),
        help="voice runtime: 'pipecat' (default) or 'stdlib' (fallback/comparison)",
    )
    parser.add_argument(
        "--backend",
        choices=BACKEND_NAMES,
        default=os.environ.get(BACKEND_ENV_VAR, STUB),
        help="conversation backend: 'stub' (default, offline) or 'http' (VOICE_BACKEND_URL)",
    )
    parser.add_argument(
        "--webrtc",
        choices=("auto", "on", "off"),
        default=os.environ.get(WEBRTC_ENV_VAR, "auto"),
        help="WebRTC streaming runtime: 'auto' (on if installed), 'on' (require), 'off'",
    )
    parser.add_argument(
        "--websocket",
        choices=("auto", "on", "off"),
        default=os.environ.get("VOICE_WEBSOCKET", "auto"),
        help="live browser WebSocket voice path (TASK-WEB-028/038): 'auto' (on if "
        "installed), 'on' (require), 'off'. On the default aiohttp server the WS rides "
        "the SAME port at /ws (ceiling VOICE_MAX_WS_SESSIONS); on the legacy stdlib "
        "server it uses a separate listener on VOICE_WS_PORT (default 8091)",
    )
    parser.add_argument(
        "--genesys",
        choices=("auto", "on", "off"),
        default=os.environ.get("VOICE_GENESYS", "auto"),
        help="Genesys Audio Connector `wss` endpoint (TASK-WEB-041): 'auto'/'on' mount "
        "GET /genesys/audiohook on the aiohttp server, 'off' disables it. Codec "
        "(VOICE_GENESYS_CODEC, default L16), concurrency (VOICE_GENESYS_MAX_SESSIONS, "
        "default 3) and the 15-min cap (VOICE_GENESYS_MAX_SESSION_S) are env-tunable",
    )
    parser.add_argument(
        "--stun",
        default=os.environ.get("VOICE_STUN", ""),
        help="comma-separated STUN URLs for the WebRTC ICE servers (optional)",
    )
    parser.add_argument(
        "--turn",
        default=os.environ.get("VOICE_TURN", ""),
        help="comma-separated TURN URLs for relayed WebRTC media (needs "
        "--turn-username/--turn-credential); required when clients cannot reach the "
        "bridge's host candidates directly (e.g. Prodpriv NAT)",
    )
    parser.add_argument(
        "--turn-username",
        default=os.environ.get("VOICE_TURN_USERNAME", ""),
        help="username for the TURN relays in --turn",
    )
    parser.add_argument(
        "--turn-credential",
        default=os.environ.get("VOICE_TURN_CREDENTIAL", ""),
        help="credential/password for the TURN relays in --turn",
    )
    parser.add_argument(
        "--stt-mode",
        choices=("streaming", "batch"),
        default=os.environ.get("VOICE_STT_MODE", "streaming"),
        help="WebRTC STT path: 'streaming' (default, Gradium WS partials) or 'batch'",
    )
    parser.add_argument(
        "--tts-mode",
        choices=("streaming", "batch"),
        default=os.environ.get("VOICE_TTS_MODE", "streaming"),
        help="WebRTC TTS path: 'streaming' (default, Gradium WS incremental) or 'batch'",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
