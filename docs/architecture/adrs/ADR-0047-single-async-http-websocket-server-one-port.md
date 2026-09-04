# ADR-0047: Single Async HTTP+WebSocket Server On One Port For The Voice Runtime

## Status

Accepted (2026-08-26, user-directed). **Implemented and shipped** in `v0.7.0` via **TASK-WEB-038**
(aiohttp single async HTTP+WebSocket server, now the default runtime) and deployed to the pilot;
the Genesys AudioHook endpoint (`/genesys/audiohook`) rides the same routed `:8090` (Sprint 13).
**Refines** — reversing one of its constraints in
the new context — [ADR-0022](ADR-0022-webrtc-transport-for-streaming-voice-loop.md) (stdlib
`http.server` + "no FastAPI"; one asyncio loop *alongside* the threaded HTTP server).
**Builds on** [ADR-0046](ADR-0046-websocket-primary-live-voice-transport.md) (WebSocket is the
primary V1 live transport) and [ADR-0043](ADR-0043-interim-websocket-audio-transport-genesys-ready.md)
(transport-agnostic session factory). **Simplifies** the edge decision of
[ADR-0038](ADR-0038-pilot-deployment-architecture-eir-ai4cc-tst.md) and makes the WS-routing
work of **TASK-WEB-037 / TASK-INFRA-010** removable. Prepares the
[ADR-0040](ADR-0040-genesys-audio-connector-v2v-media-plane.md) Genesys Audio Connector
`wss://` endpoint.

## Context

[ADR-0022](ADR-0022-webrtc-transport-for-streaming-voice-loop.md) built the streaming voice
loop as a WebRTC path *alongside* the existing batch HTTP server, and made two deliberate
choices for that context:

- **Keep the stdlib `http.server`** (`ThreadingHTTPServer` + `BaseHTTPRequestHandler`) for the
  UI, the REST routes (`/api/voice/stt|tts|turn`, `/api/voice/webrtc/offer`, `openapi.yaml`)
  and the WebRTC signaling handshake, and **avoid FastAPI** — "don't drag a second web
  framework into a stdlib server for a two-endpoint handshake".
- Run **one persistent asyncio loop** on a daemon thread (`web_voice/async_loop.py`) for the
  media session, with threaded HTTP handlers submitting coroutines to it.

That was correct when WebRTC was an experimental add-on and the WebSocket path did not exist.
When the interim WebSocket transport landed (ADR-0043, Sprint 12) it was implemented with
Pipecat's `SingleClientWebsocketServerTransport`, which runs **its own listener on a second
port** (`:8091`, `VOICE_WS_PORT`), driven by the same background loop. The runtime therefore
exposes **two servers on two ports**:

```
Bridge container
├─ :8090  stdlib ThreadingHTTPServer   → UI, /api/voice/* REST, WebRTC signaling
└─ :8091  Pipecat websockets listener  → live full-duplex PCM16 audio (single client)
```

[ADR-0046](ADR-0046-websocket-primary-live-voice-transport.md) then made **WebSocket the
primary V1 live transport** (web + Genesys). In that new context, the two-port split has three
concrete costs it did not have before:

1. **It forces an edge special-case and a platform dependency.** Because the WS lives on a
   *different* port than the routed `:8090`, the public VIP must be taught to detect the
   WebSocket upgrade and route it to `:8091` (the `acl is_voice_ws` + `voice_ws` backend of
   **TASK-WEB-037 / TASK-INFRA-010**). HAProxy runs on the platform-managed `[lb]` nodes
   (`inventory/hosts.ini`: "reference / future automation only"), so applying that route needs
   the platform team. **If HTTP and WebSocket shared one port, HAProxy in `mode http` would
   tunnel the `Connection: upgrade` on the existing `voice_bridges` backend with no config
   change** (the global `timeout tunnel` is already set) — the edge special-case and the
   platform dependency both disappear.
2. **It caps concurrency at one call per bridge.** `SingleClientWebsocketServerTransport` is
   single-client per listener (`DEFAULT_MAX_WS_SESSIONS = 1`), which also produced the awkward
   `balance source` "call affinity" discussion. A single async server can accept N WebSocket
   connections and instantiate one session per connection.
3. **It grows the operational surface**: two published ports, an extra firewall rule
   (`firewall_extra_ports: [8091]`), two health semantics.

The business logic is already transport-neutral (ADR-0043's session factory; the STT/answer/TTS
`FrameProcessor`s and `BackendAnswerPort` are reused unchanged across WebRTC/WS), and **one
asyncio loop already exists**. The stdlib threaded HTTP server is now the odd component out.

## Decision

**Unify the voice runtime onto a single asynchronous HTTP + WebSocket server listening on one
port**, running on the `BackgroundEventLoop` that already exists. One listener serves:

- the **static UI** (`index.html`, `ws.html`, `webrtc.html`, JS assets);
- the **REST routes** (`/api/voice/stt|tts|turn`, `openapi.yaml`, and — for the dev path —
  `/api/voice/webrtc/offer`);
- the **live-audio WebSocket upgrade** (the primary transport), handed to the ADR-0043
  transport-agnostic session factory.

Concrete choices:

1. **Framework: `aiohttp` (preferred), confirmed by the TASK-WEB-038 spike.** aiohttp serves
   static files + REST + a WebSocket route on one asyncio app with a much smaller footprint
   than FastAPI/uvicorn (no pydantic, no separate ASGI server). ADR-0022's "no FastAPI" concern
   was *don't add a heavy framework for a two-endpoint handshake*; that concern is honoured by
   choosing the lightest option that removes the second listener — not by keeping the stdlib.
   The spike confirms Python 3.14 wheels on the internal mirror and the static+REST+WS surface
   before the build commits.
2. **One port.** The runtime binds a single port (default the existing `:8090`); `VOICE_WS_PORT`
   and the second published port are retired. The WebSocket is reached **same-origin** (already
   how `ws.js` connects post-TASK-WEB-037).
3. **Reuse, don't fork the domain.** The session factory, control-signal seam, providers and
   backend client are unchanged — this is a transport/adapter-layer change (hexagonal boundary),
   not a domain change. The batch `/api/voice/turn` contract (ADR-0016 fallback, BUG-015) is
   preserved and re-tested.
4. **Concurrency.** Accept multiple concurrent WebSocket connections, one session per
   connection, lifting the single-client cap; a per-bridge ceiling stays configurable for
   backpressure (mirrors the WebRTC `VOICE_MAX_WEBRTC_SESSIONS`).
5. **WebRTC (dev-only, ADR-0046) signaling** either moves into the aiohttp app as one more
   route or stays as-is behind its import guard; it is no longer on the primary path.

**Edge consequence made explicit:** once HTTP and WebSocket share one routed port, the
TASK-WEB-037 HAProxy `voice_ws` ACL/backend + the `firewall_extra_ports: [8091]` opening become
**removable**; the existing single `voice_bridges` backend tunnels the upgrade. TASK-WEB-037
remains valid as the **bridge** (it makes `wss://<vip>/` work *before* this refactor); this ADR
is the **destination** that removes the special-case.

## Consequences

**Positive**

- **Removes the edge special-case and the platform-team dependency** for WS routing: one routed
  port, HAProxy tunnels the upgrade with no LB config change.
- **Lifts the one-call-per-bridge cap** — real multi-session concurrency for the pilot.
- **Right foundation for Genesys Audio Connector** (ADR-0040): a proper async HTTP+WS server is
  the natural place to expose the AudioHook `wss://` endpoint.
- Smaller operational surface: one port, one firewall rule, one health check.
- Retires the ADR-0022 RF-012-era hybrid (threaded HTTP + side loop) for a single coherent
  async runtime; the loop is already there.

**Negative / risks**

- A **real refactor of a validated path**: the batch `/api/voice/turn` loop (BUG-015) and the
  REST handlers move from `BaseHTTPRequestHandler` to async handlers → regression risk; must be
  covered by the existing unit + behave suites before/after.
- **New dependency** (`aiohttp`) and its transitive wheels on the internal mirror (spike gate).
  Footprint is already large (pipecat + websockets + av + opencv), so the marginal cost is small.
- **Re-introduces an HTTP framework** that ADR-0022 avoided — accepted deliberately now that the
  WebSocket is primary and the stdlib server is the blocker, not the saver.
- WebRTC signaling code must be re-homed or explicitly kept behind its guard.

**Neutral**

- Provider/transport agnosticism is unchanged (ADR-0012/0043): STT/TTS stay behind their ports;
  only the *serving* layer changes.
- No change to the backend (Java) or the RAG/guardrail path.

## Alternatives Considered

- **Keep two ports + the HAProxy demux (status quo / TASK-WEB-037 as the end-state):** rejected
  as the destination — it hard-codes a platform-team dependency into every deploy and keeps the
  one-call-per-bridge cap. Retained only as the interim bridge until this refactor ships.
- **In-container reverse proxy (nginx/traefik) demuxing one published port → the two internal
  servers:** rejected — adds a component and config to every image, does **not** fix the
  concurrency cap, and does not simplify the application (the two servers still exist).
- **FastAPI + uvicorn:** viable but heavier than aiohttp (pydantic, a separate ASGI server) for
  a small static+REST+WS surface; kept as the spike's fallback if aiohttp cannot serve the
  surface cleanly on Python 3.14.
- **Serve HTTP from the `websockets` library's `process_request` hook (no new framework):**
  rejected — rebuilds a static-file + REST layer inside a WebSocket server, and Pipecat's
  transport wraps that server so the hook is not cleanly ours to own.
- **Async-refactor at ADR-0022 time (rejected then):** correctly rejected in the WebRTC-add-on
  context; this ADR does not rewrite that history, it records that ADR-0046 changed the premise.

## Related Documents

- Primary-transport decision: [ADR-0046](ADR-0046-websocket-primary-live-voice-transport.md)
- Original stdlib/loop choice being refined: [ADR-0022](ADR-0022-webrtc-transport-for-streaming-voice-loop.md)
- Session factory reused: [ADR-0043](ADR-0043-interim-websocket-audio-transport-genesys-ready.md)
- Genesys media plane this prepares: [ADR-0040](ADR-0040-genesys-audio-connector-v2v-media-plane.md)
- Edge/deploy topology simplified: [ADR-0038](ADR-0038-pilot-deployment-architecture-eir-ai4cc-tst.md), `deploy/haproxy/README.md`
- Interim edge bridge this makes removable: TASK-WEB-037 / TASK-INFRA-010 (`product-backlog/tasks/web-voice-tasks.md`)
- Implementation ticket: **TASK-WEB-038** (`product-backlog/tasks/web-voice-tasks.md`)
- Latency gate to re-validate after the refactor: [ADR-0029](ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md)
