"""TASK-WEB-038 spike verification — no manual steps.

Boots the single aiohttp app on an ephemeral port and asserts that, on ONE
port, all four surfaces work:

  1. GET  /                 -> 200, static HTML          (static serving)
  2. GET  /api/voice/meta   -> 200, JSON                 (REST route)
  3. POST /api/voice/turn   -> 200, JSON success shape   (batch contract)
  4. GET  /ws               -> 101 upgrade + echo         (WebSocket, same port)

Also records the footprint (aiohttp version, cold app-build time, first-byte
time) so the ADR-0047 decision has numbers. Exits non-zero on any failure.
"""

from __future__ import annotations

import asyncio
import sys
import time

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from server import make_app  # noqa: E402


async def run() -> int:
    checks: list[tuple[str, bool, str]] = []

    t0 = time.perf_counter()
    app = make_app()
    build_ms = (time.perf_counter() - t0) * 1000

    server = TestServer(app)
    await server.start_server()
    base = server.make_url("")

    async with aiohttp.ClientSession() as session:
        # 1. static index
        t = time.perf_counter()
        async with session.get(base.with_path("/")) as r:
            body = await r.text()
            first_byte_ms = (time.perf_counter() - t) * 1000
            checks.append(
                ("GET / (static)", r.status == 200 and "spike" in body, f"status={r.status}")
            )

        # 2. REST meta
        async with session.get(base.with_path("/api/voice/meta")) as r:
            data = await r.json()
            ok = r.status == 200 and data.get("port_model") == "single"
            checks.append(("GET /api/voice/meta", ok, f"status={r.status} body={data}"))

        # 3. batch turn contract
        async with session.post(
            base.with_path("/api/voice/turn"),
            data=b"\x00\x01" * 512,
            headers={"x-correlation-id": "spike-verify"},
        ) as r:
            data = await r.json()
            ok = (
                r.status == 200
                and data.get("audio_bytes_in") == 1024
                and data.get("correlation_id") == "spike-verify"
                and "answer" in data
            )
            checks.append(("POST /api/voice/turn", ok, f"status={r.status} bytes_in={data.get('audio_bytes_in')}"))

        # 4. WebSocket upgrade on the SAME port + echo (binary + control)
        async with session.ws_connect(base.with_path("/ws")) as ws:
            pcm = b"\x10\x20" * 800  # fake PCM16 frame
            await ws.send_bytes(pcm)
            echoed = await ws.receive(timeout=5)
            bin_ok = echoed.type == aiohttp.WSMsgType.BINARY and echoed.data == pcm

            await ws.send_json({"type": "start_of_speech", "language": "fr"})
            ctrl = await ws.receive(timeout=5)
            ctrl_ok = (
                ctrl.type == aiohttp.WSMsgType.TEXT
                and ctrl.json().get("echo", {}).get("type") == "start_of_speech"
            )
            await ws.send_json({"type": "close"})
            checks.append(("GET /ws (101 upgrade + echo)", bin_ok and ctrl_ok, f"bin={bin_ok} ctrl={ctrl_ok}"))

    await server.close()

    print("=" * 68)
    print("TASK-WEB-038 aiohttp one-port spike — verification")
    print("=" * 68)
    print(f"aiohttp        : {aiohttp.__version__}")
    print(f"python         : {sys.version.split()[0]}")
    print(f"app build      : {build_ms:.2f} ms (cold, in-process)")
    print(f"first byte GET/: {first_byte_ms:.2f} ms")
    print("-" * 68)
    all_ok = True
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<32} {detail}")
        all_ok = all_ok and ok
    print("-" * 68)
    print("RESULT:", "ALL PASS — one port serves static + REST + WS" if all_ok else "FAILURES PRESENT")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
