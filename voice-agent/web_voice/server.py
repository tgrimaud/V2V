"""Minimal web voice runtime server (TASK-WEB-001, TASK-WEB-005).

Serves the mic-capture page and exposes the voice endpoints:
- `POST /api/voice/stt`  PCM16 mono 16 kHz audio in -> transcript JSON out.
- `POST /api/voice/tts`  `?text=` in -> WAV audio out.
- `POST /api/voice/turn` PCM16 audio in -> full STT -> backend answer -> TTS loop ->
  WAV out (transcript + answer text returned as `X-Voice-*` headers).

The runtime is selected at startup (`--runtime {stdlib,pipecat}`, env `VOICE_RUNTIME`):
the server drives a `VoiceTurnProcessor` seam, so the stdlib and Pipecat runtimes
coexist and produce identical output. The STT/TTS provider is selected with
`--provider`, defaulting to Gradium with a fixture fallback for offline development.
"""

import argparse
import json
import os
import socketserver
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conversation_backend import BACKEND_NAMES, STUB, build_backend  # noqa: E402
from stt_validation.models import SttOutcome  # noqa: E402
from stt_validation.provider_factory import GRADIUM, PROVIDER_NAMES, build_provider  # noqa: E402
from tts_synthesis.provider_factory import build_provider as build_tts_provider  # noqa: E402
from voice_common.telemetry import TelemetryRecorder, Timer  # noqa: E402

from .egress import WebVoiceEgress  # noqa: E402
from .envelope import ChannelEnvelope  # noqa: E402
from .ingress import WebVoiceIngress  # noqa: E402
from .runtime import (  # noqa: E402
    DEFAULT_RUNTIME,
    RUNTIME_NAMES,
    VoiceTurnProcessor,
    build_turn_processor,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STT_ROUTE = "/api/voice/stt"
TTS_ROUTE = "/api/voice/tts"
TURN_ROUTE = "/api/voice/turn"
WEBRTC_OFFER_ROUTE = "/api/voice/webrtc/offer"
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
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlparse(self.path).path
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            filename = "index.html" if path in ("/", "") else path.lstrip("/")
            self._serve_static(filename)

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = urlparse(self.path).path
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
            status = 200 if result.outcome is SttOutcome.SUCCESS else 502
            self._send_json(status, result.to_dict())

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
                self._send_json(502, response.result.to_dict())
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
                self._send_json(502, transcript.to_dict() if transcript else {"error": "no_transcript"})
                return
            response = result.tts_response
            if response is None or response.wav is None:
                _log_turn(telemetry)
                self._send_json(502, response.result.to_dict() if response else {"error": "no_audio"})
                return
            send = Timer()
            self._send_wav(response.wav, _answer_headers(transcript, result.answer_result))
            processor.record_egress(response, envelope, telemetry, sent_ms=send.elapsed_ms())
            _log_turn(telemetry)

        def _read_body(self) -> bytes | None:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length > MAX_AUDIO_BYTES:
                return None
            return self.rfile.read(length) if length else b""

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

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_wav(self, wav: bytes, extra_headers: dict[str, str] | None = None) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(wav)

        def log_message(self, *_args) -> None:  # silence default per-request stderr noise
            return

    return WebVoiceHandler


def _answer_headers(transcript, answer) -> dict[str, str]:
    """Expose the transcript + spoken answer to the same client on a `/turn` reply.

    The `/turn` body is the answer WAV; these headers let the page still show what was
    asked and what is being said, plus the correlation id, without a second request.
    Text is percent-encoded (UTF-8) so accented characters are header-safe; it is sent
    only to the requesting client and never written to server logs.
    """
    headers: dict[str, str] = {}
    if transcript is not None:
        headers["X-Correlation-Id"] = transcript.correlation_id
        headers["X-Voice-Transcript"] = quote(transcript.transcript)
    if answer is not None:
        headers["X-Voice-Answer"] = quote(answer.text)
        headers["X-Answer-Provider"] = answer.provider
        headers["X-Answer-Outcome"] = answer.outcome.value
        # Degraded reason is a stable, non-sensitive code (e.g. backend_unavailable)
        # so the client/QA can see *why* a safe fallback was spoken (TASK-WEB-003-F).
        if answer.degraded_reason:
            headers["X-Answer-Degraded-Reason"] = answer.degraded_reason
    return headers


def _envelope_from_query(query: str) -> ChannelEnvelope:
    params = parse_qs(query)
    return ChannelEnvelope.for_web_turn(
        conversation_id=_first(params, "conversation_id"),
        external_session_id=_first(params, "session_id"),
        correlation_id=_first(params, "correlation_id"),
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
    ice = [s for s in (args.stun or "").split(",") if s]
    signaling = WebRtcSignalingService(
        ingress=ingress, egress=egress, backend=backend, loop=loop, ice_servers=ice
    )
    return signaling, loop


def main() -> int:
    args = _parse_args()
    ingress = WebVoiceIngress(build_provider(args.provider))
    egress = WebVoiceEgress(build_tts_provider(args.provider))
    # `stub` (default) is the deterministic offline answer; `http` targets a real
    # conversation endpoint configured via VOICE_BACKEND_URL (TASK-WEB-003-C).
    backend = build_backend(args.backend)
    processor = build_turn_processor(args.runtime, ingress, egress, backend)
    signaling, loop = _build_signaling(args, ingress, egress, backend)
    server = WebVoiceHTTPServer((args.host, args.port), build_handler(processor, signaling))
    print(
        f"Web voice server on http://{args.host}:{args.port} "
        f"(provider={args.provider}, runtime={args.runtime}, backend={backend.name}, "
        f"webrtc={'on' if signaling else 'off'})",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    finally:
        if signaling is not None:
            signaling.close()
        if loop is not None:
            loop.stop()
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the web voice runtime server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
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
        "--stun",
        default=os.environ.get("VOICE_STUN", ""),
        help="comma-separated STUN/TURN URLs for the WebRTC ICE servers (optional)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
