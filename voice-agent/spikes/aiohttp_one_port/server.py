"""TASK-WEB-038 spike: one async HTTP + WebSocket server on ONE port (aiohttp).

Goal (ADR-0047): prove a single asyncio aiohttp application can serve, on one
port, everything the voice runtime exposes today across two ports / two servers:

  * static files (`/`, `/ws.html`, ...)          -> today: stdlib ThreadingHTTPServer :8090
  * REST `/api/voice/*` (batch `/turn`, meta)     -> today: stdlib ThreadingHTTPServer :8090
  * a WebSocket upgrade (live audio transport)    -> today: pipecat websockets server :8091

This is a THROWAWAY proof of routing/plumbing only. It does NOT wire the real
STT/answer/TTS session factory (ADR-0043) — that stays a transport-agnostic
adapter swap in the full TASK-WEB-038 build. The handlers here are deterministic
stubs so the spike has no provider dependency.

Run standalone:
    ./.venv/bin/python spikes/aiohttp_one_port/server.py --port 8099
Verify (no manual steps):
    ./.venv/bin/python spikes/aiohttp_one_port/verify.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aiohttp import WSMsgType, web

STATIC_DIR = Path(__file__).parent / "static"

# Binary WS frames carry PCM16 audio (same internal boundary as ADR-0043:
# PCM16 / 16 kHz mono). Text WS frames carry JSON control signals. The spike
# echoes both to prove full-duplex on the upgraded connection.


async def handle_index(request: web.Request) -> web.Response:
    """Static index — proves static serving on the same app as the API + WS."""
    index = STATIC_DIR / "index.html"
    return web.FileResponse(index)


async def handle_meta(request: web.Request) -> web.Response:
    """Cheap health/meta route (mirrors the runtime's `GET /` liveness use)."""
    return web.json_response(
        {
            "service": "aiohttp-one-port-spike",
            "transports": ["http", "websocket"],
            "port_model": "single",
            "adr": "ADR-0047",
        }
    )


async def handle_voice_turn(request: web.Request) -> web.Response:
    """Batch `/api/voice/turn` shape (TASK-WEB-034 JSON contract), stubbed.

    Accepts an audio body, returns the one-JSON-object success shape the real
    endpoint uses (base64 WAV omitted here — deterministic stub). Proves the
    batch HTTP contract lives happily on the same app as the WS upgrade.
    """
    body = await request.read()
    return web.json_response(
        {
            "transcript": "stub transcript",
            "answer": "stub answer",
            "audio_bytes_in": len(body),
            "audio_base64": "",  # real endpoint returns the WAV here
            "correlation_id": request.headers.get("x-correlation-id", "spike"),
        }
    )


async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket upgrade on the SAME port/app — the crux of the spike.

    Echoes binary PCM (audio) and JSON control frames, matching the ADR-0043
    framing split. In the full build this hands the socket to the shared
    transport-agnostic SessionFactory instead of echoing.
    """
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    async for msg in ws:
        if msg.type == WSMsgType.BINARY:
            # audio frame -> would feed STT; echo back as "return audio"
            await ws.send_bytes(msg.data)
        elif msg.type == WSMsgType.TEXT:
            try:
                control = json.loads(msg.data)
            except json.JSONDecodeError:
                control = {"raw": msg.data}
            await ws.send_json({"echo": control})
            if control.get("type") == "close":
                await ws.close()
        elif msg.type == WSMsgType.ERROR:
            break

    return ws


def make_app() -> web.Application:
    """Build the single aiohttp application (used by both server + verify)."""
    app = web.Application()
    app.add_routes(
        [
            web.get("/", handle_index),
            web.get("/api/voice/meta", handle_meta),
            web.post("/api/voice/turn", handle_voice_turn),
            web.get("/ws", handle_ws),
        ]
    )
    # Static assets under /static (ws.html/ws.js would live here in the real app).
    app.router.add_static("/static/", STATIC_DIR, show_index=False)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()
    web.run_app(make_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
