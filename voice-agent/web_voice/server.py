"""Minimal web voice ingress server (TASK-WEB-001).

Serves the mic-capture page and exposes `POST /api/voice/stt`, which accepts raw
PCM16 mono 16 kHz audio and returns the transcript (or a sanitized failure). It
uses only the Python standard library so the voice runtime needs no new
dependency; the STT provider is selected at runtime (`--provider`), defaulting to
Gradium for live capture with a fixture fallback for offline development.
"""

import argparse
import json
import socketserver
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stt_validation.models import SttOutcome  # noqa: E402
from stt_validation.provider_factory import GRADIUM, PROVIDER_NAMES, build_provider  # noqa: E402
from stt_validation.telemetry import TelemetryRecorder, Timer  # noqa: E402

from .envelope import ChannelEnvelope  # noqa: E402
from .ingress import WebVoiceIngress  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
STT_ROUTE = "/api/voice/stt"
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # guard against oversized uploads (~13 min PCM16 16k)
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


def build_handler(ingress: WebVoiceIngress) -> type[BaseHTTPRequestHandler]:
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
            if urlparse(self.path).path != STT_ROUTE:
                self._send_json(404, {"error": "not_found"})
                return
            self._handle_stt()

        def _handle_stt(self) -> None:
            receive = Timer()
            audio = self._read_body()
            received_ms = receive.elapsed_ms()
            if audio is None:
                self._send_json(413, {"error": "audio_too_large"})
                return
            envelope = _envelope_from_query(urlparse(self.path).query)
            telemetry = TelemetryRecorder()
            result = ingress.transcribe_turn(audio, envelope, telemetry, received_ms=received_ms)
            _log_turn(telemetry)
            status = 200 if result.outcome is SttOutcome.SUCCESS else 502
            self._send_json(status, result.to_dict())

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

        def log_message(self, *_args) -> None:  # silence default per-request stderr noise
            return

    return WebVoiceHandler


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


def main() -> int:
    args = _parse_args()
    ingress = WebVoiceIngress(build_provider(args.provider))
    server = WebVoiceHTTPServer((args.host, args.port), build_handler(ingress))
    print(f"Web voice ingress on http://{args.host}:{args.port} (provider={args.provider})", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the web voice STT ingress server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--provider", choices=PROVIDER_NAMES, default=GRADIUM)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
