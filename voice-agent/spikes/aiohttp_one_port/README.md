# TASK-WEB-038 spike — one async HTTP + WebSocket server on ONE port (aiohttp)

**Ticket:** TASK-WEB-038 · **Decision:** [ADR-0047](../../../docs/architecture/adrs/ADR-0047-single-async-http-websocket-server-one-port.md)
**Date:** 2026-08-26 · **Status:** ✅ spike PASS (throwaway PoC, no provider wiring)

## Question the spike answers

ADR-0047 wants the voice runtime unified onto a **single async server on one routed
port**, retiring today's two-port split (stdlib `ThreadingHTTPServer` :8090 for
static + `/api/voice/*`, and a separate pipecat websockets server :8091). That lets
HAProxy `mode http` tunnel the WebSocket upgrade on the **existing** `voice_bridges`
backend (`timeout tunnel`) — no `voice_ws` ACL, no second backend, no firewall
opening, no platform-team edge dependency (TASK-INFRA-010 dropped) — and lifts the
one-call-per-bridge cap.

Open question before committing: **can aiohttp serve static + the `/api/voice/*` REST
routes + a WebSocket upgrade on one asyncio app, with Python 3.14 wheels available,
without pulling a heavy new dependency stack?**

## Result: yes

```
aiohttp        : 3.14.1
python         : 3.14.2
app build      : 0.34 ms (cold, in-process)
first byte GET/: 15.44 ms
[PASS] GET / (static)
[PASS] GET /api/voice/meta            (REST route)
[PASS] POST /api/voice/turn           (batch JSON contract shape)
[PASS] GET /ws (101 upgrade + echo)   (WebSocket, SAME port, binary PCM + JSON control)
RESULT: ALL PASS — one port serves static + REST + WS
```

Reproduce:

```bash
cd voice-agent
./.venv/bin/python spikes/aiohttp_one_port/verify.py     # asserts all 4 surfaces, exits non-zero on failure
# or run it and poke by hand:
./.venv/bin/python spikes/aiohttp_one_port/server.py --port 8099
```

## Footprint — the decisive point vs FastAPI

**aiohttp is already installed**, transitively via `pipecat-ai` / `aiortc`
(`aiohttp 3.14.1`; core deps `aiohappyeyeballs`, `aiosignal`, `attrs`, `frozenlist`,
`multidict`, `propcache`, `yarl` all already present). Adopting it as a direct
dependency adds **zero new wheels** to the voice image and **zero** to build/startup
weight. Python 3.14 wheels are present and working (success criterion met).

By contrast, FastAPI would add `starlette` + `pydantic`(+`pydantic-core` Rust) +
an ASGI server (`uvicorn`) — a new stack for no benefit here, and it is exactly the
framework weight ADR-0022 rejected. aiohttp keeps ADR-0022's "no heavy framework"
spirit while enabling the single-port async model ADR-0047 wants.

## What the spike deliberately does NOT do

- No real STT / answer / TTS. Handlers are deterministic stubs. The full build wires
  the WS handler to the **transport-agnostic `SessionFactory`** (ADR-0043) — the same
  session WebRTC + the pipecat WS socle already build — so business logic and the
  domain are unchanged (adapter-layer change only).
- No concurrency lift yet. The spike proves routing; the full build lifts the socle's
  one-call-per-bridge cap to N concurrent WS sessions (each its own `SessionFactory`
  session on the shared loop) with the TASK-WEB-030 capacity ceiling + backpressure.
- No batch-`/turn` behaviour change. The real `/api/voice/turn` (TASK-WEB-034 JSON
  contract, BUG-015 full-answer WAV) is ported as-is onto an aiohttp handler.

## Integration notes for the full TASK-WEB-038 build

1. Replace the stdlib `ThreadingHTTPServer` (`web_voice/`) HTTP + static serving with
   aiohttp routes on `make_app()`; keep the exact `/api/voice/*` paths + JSON shapes
   (openapi drift guard, TASK-WEB-016, must stay green).
2. Replace the separate pipecat websockets server (:8091) with an aiohttp `GET /ws`
   (or `/api/voice/ws`) upgrade handler that hands the socket to `SessionFactory`.
   Retire `VOICE_WS_PORT` / the `:8091` publish once one port is proven live.
3. One persistent asyncio loop already exists (`web_voice/async_loop.py`); aiohttp is
   loop-native, so the `run_coroutine_threadsafe` bridging the stdlib server needed
   goes away.
4. Preserve US-036 per-slice telemetry emission (TASK-WEB-030 `build_payload`) and the
   control-signal seam (TASK-WEB-029) unchanged — they sit above the transport.
5. Edge: no HAProxy change — `mode http` + `timeout tunnel` tunnels the upgrade on the
   existing `voice_bridges` backend (already reverted the TASK-WEB-037 `voice_ws`
   reference route). Re-run `qa-validate-haproxy.sh`.
6. Re-measure ADR-0029 on `wss://<vip>/` (single port through HAProxy) — this also
   removes the SSH-tunnel/loopback workaround the TASK-WEB-039 sample needed.

## Rough sizing (for planning, not a commitment)

| Slice of the full build | Estimate |
|---|---|
| Port static + `/api/voice/*` REST onto aiohttp (+ openapi drift guard green) | ~1 day |
| WS upgrade handler → `SessionFactory`; retire the :8091 server + `VOICE_WS_PORT` | ~1–1.5 days |
| Concurrency lift (N sessions) + TASK-WEB-030 ceiling/backpressure re-home | ~1 day |
| Compose/Ansible cleanup (drop 8091 publish + dead `firewall_extra_ports`) + edge re-QA | ~0.5 day |
| Live ADR-0029 re-measure on `wss://<vip>/` + adversarial review + QA | ~1 day |

## Verdict

Proceed with **aiohttp** for TASK-WEB-038 (ADR-0047 confirmed). Zero-new-dependency,
Python 3.14-ready, one port serves static + REST + WS. FASTAPI rejected (needless
weight). This directory is throwaway; delete it when the full build lands.
