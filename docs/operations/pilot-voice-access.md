# Pilot Voice Access — Entry Points And Transport Status

## Objective

Give operations and QA a single place to answer "how do I reach the voice bot on
the pilot, and what actually works today?". It documents the browser entry points
(batch one-shot, the **primary live WebSocket** transport, and the optional/dev
WebRTC page), the deployment topology behind the voice VIP, and why WebRTC media
does not establish for remote clients (expected — it is a same-subnet/dev path now).

> **Transport direction (ADR-0046, 2026-08-26):** the **WebSocket** audio tunnel
> (`ws.html`, `wss://<vip>/`, routed by HAProxy to the bridges' `:8091`) is the
> **primary V1 live voice transport** for web and the substrate for Genesys Audio
> Connector. **WebRTC is demoted to an optional same-subnet / dev-only path** — it is
> kept (not deleted) but is not the pilot's remote live path. TASK-WEB-037 tracks the
> edge wiring; see [ADR-0046](../architecture/adrs/ADR-0046-websocket-primary-live-voice-transport.md).

This is an access/runbook note. The signaling contract itself lives in
[`../architecture/voice-runtime-http-contract.md`](../architecture/voice-runtime-http-contract.md);
the media-plane decision lives in
[`../architecture/adrs/ADR-0042-no-turn-for-pilot-genesys-audio-connector-external-media.md`](../architecture/adrs/ADR-0042-no-turn-for-pilot-genesys-audio-connector-external-media.md).

## Scope

- Environment: pilot `eir-ai4cc-tst` — voice bridges `vla-ai4cc-t01/t02.prod.lan`
  (`.103/.104`), one bridge per VM, behind the voice VIP
  `https://vip-ai4cc-voice-t01.prod.lan/` (`.10`, HAProxy TLS edge).
- The voice bridge image binds `0.0.0.0:8090` (HTTP) **and** `0.0.0.0:8091` (live
  WebSocket, ADR-0046). HAProxy terminates TLS on `:443` and routes HTTP to
  `vla-t01/t02:8090`. **Edge decision (ADR-0047):** the WebSocket will ride the same
  routed `:8090` once the runtime unifies HTTP+WS on one port (TASK-WEB-038), so
  HAProxy tunnels the `Upgrade` on the existing backend — **no `:8091` route at the
  edge**. Until then, `:8091` is exercised **directly** (same-subnet or SSH tunnel),
  not through the VIP.

## Entry Points

The voice bridge serves the HTTP clients (batch + WebRTC signaling/UI) from its
`:8090` server and the live WebSocket audio from its `:8091` server. The target is a
**single routed port** (ADR-0047): the browser reaches all of them through the same
VIP origin once the runtime unifies on one port. Until TASK-WEB-038 lands, the live
WebSocket is validated **direct-to-bridge** (see [Live-latency test without HAProxy](#live-latency-test-without-haproxy)).

| Channel | Browser URL | Signaling / API endpoint | Media |
|---------|-------------|--------------------------|-------|
| **Live WebSocket (primary, ADR-0046)** | target: `…/ws.html` on the VIP · interim: `http://<bridge>:8090/ws.html` (direct) | target: `wss://<vip>/` (same origin, tunnelled on the existing backend — ADR-0047) · interim: `ws://<bridge>:8091/` | PCM16/16 kHz over **one WS tunnel** (TCP, no TURN) |
| Batch one-shot (validated) | `https://vip-ai4cc-voice-t01.prod.lan/` (serves `index.html`) | `POST /api/voice/turn` (PCM16 in → full-answer WAV out) | HTTP response body over HTTPS (through HAProxy) |
| Streaming WebRTC (optional / same-subnet / dev) | `https://vip-ai4cc-voice-t01.prod.lan/webrtc.html` | `POST /api/voice/webrtc/offer` (SDP offer → SDP answer) | RTP/SRTP over **UDP**, peer-to-peer with the answering bridge — **not** through HAProxy; needs same-subnet or STUN/TURN |

Notes:

- `GET /` returns `index.html` (batch). Any other path is served as a static file,
  so the WebSocket UI is reached at **`/ws.html`** (paired with `ws.js`) and the
  WebRTC UI at **`/webrtc.html`** (paired with `webrtc.js`).
- `ws.js` connects **same-origin** (`wss://<host>/` on `:443`) when served over HTTPS,
  so the socket rides the VIP with the page — this is the target (ADR-0047, one routed
  port). Served over plain HTTP it connects **direct** to `ws://<host>:8091/`;
  `?wsport=<n>` forces a specific direct port for dev/testing.
- Other endpoints on the same server: `POST /api/voice/stt`, `POST /api/voice/tts`,
  and `GET /api/voice/openapi.yaml`.

## What Works Today

- **Live WebSocket is the primary transport (ADR-0046).** Audio streams full-duplex
  (mic PCM16 up, bot PCM16 down) over one WS tunnel, with no TURN. The **target** edge
  path is `wss://<vip>/` tunnelled on the existing backend once the runtime serves WS on
  the routed `:8090` (ADR-0047 / TASK-WEB-038 — **no HAProxy change**). Until then, the
  WS turn is validated **direct-to-bridge** on `:8091` (below); measure one full live
  turn before declaring the pilot live path GO.
- **Batch one-shot is a validated fallback path.** Open the VIP root, record a
  question, and the full multi-sentence answer is transcribed, answered and spoken
  back in one HTTP turn (validated on `v0.5.2`, BUG-015).
- **WebRTC signaling is live** on the bridges (optional/dev path): the image ships
  the `pipecat-ai[webrtc]` runtime and starts with `--webrtc auto`, so
  `POST /api/voice/webrtc/offer` negotiates an SDP answer — but media only connects
  same-subnet (see below).

<a id="live-latency-test-without-haproxy"></a>
### Live-latency test without HAProxy (interim, ADR-0047)

We do **not** modify the HAProxy config to route the WebSocket: the runtime will fold
HTTP+WS onto one routed port (TASK-WEB-038) and HAProxy will tunnel the upgrade on the
existing backend. Until then, drive a real live `ws` turn **direct-to-bridge**, off the
VIP — the server emits per-call US-036 telemetry on disconnect, scored against the
ADR-0029 gate. Open an SSH tunnel to a bridge's published `:8091`, then run the headless
client from a repo checkout:

```bash
# terminal 1 — tunnel the bridge's published WS port to localhost
ssh -i ~/.ssh/id_itsf -N -L 8091:127.0.0.1:8091 grimaud@vla-ai4cc-t01.prod.lan

# terminal 2 — drive a warm live turn (real Gradium STT/TTS + Mistral on the bridge)
cd voice-agent
for i in $(seq 1 12); do
  .venv/bin/python scripts/ws_live_client.py --url ws://127.0.0.1:8091 \
    --audio fixtures/long/billing-question.pcm --language fr --hold 12
done
```

The bridge prints one telemetry JSON per call to its container logs
(`docker logs`/`podman logs`); collect them and score with
`scripts/streaming_latency_report.py --channel web --provider gradium-streaming --warm`.
No HAProxy, no TLS, no edge change. (A browser can do the same via
`http://localhost:8090/ws.html` over the tunnel — plain HTTP → `ws://localhost:8091/`,
no mixed-content block.)

Once TASK-WEB-038 lands, verify the target edge path (expects `101 Switching Protocols`
from a bridge, not the `200` UI page):

```bash
curl -sv --http1.1 -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: $(openssl rand -base64 16)" \
  https://vip-ai4cc-voice-t01.prod.lan/ 2>&1 | grep -i '< HTTP'
```

Verify WebRTC signaling is active on a node (out-of-band, not through the VIP):

```bash
# 502 webrtc_negotiation_failed = signaling is ON (empty offer is invalid, as expected).
# 503 webrtc_unavailable        = signaling is OFF (webrtc extra missing / --webrtc off).
ssh -i ~/.ssh/id_itsf grimaud@vla-ai4cc-t01.prod.lan \
  'IP=$(hostname -I | awk "{print \$1}"); \
   curl -s -m 6 -X POST -H "Content-Type: application/json" -d "{}" \
     -w "\nHTTP %{http_code}\n" http://$IP:8090/api/voice/webrtc/offer'
```

## WebRTC Media Does Not Establish For Remote Clients — Expected (Optional/Dev Path)

Since ADR-0046 this is **expected, not a defect**: WebRTC is the optional
same-subnet/dev path and the live pilot uses the WebSocket transport instead.
Signaling succeeding does **not** mean WebRTC audio flows. On the pilot:

- **HAProxy carries HTTP and (target) the WebSocket tunnel on one routed port**
  (HTTPS; ADR-0047 tunnels the upgrade on the existing backend — no special-case).
  WebRTC media is UDP peer-to-peer and never traverses HAProxy — see
  [`../../deploy/haproxy/README.md`](../../deploy/haproxy/README.md).
- **No STUN/TURN** is configured (`VOICE_STUN` / `VOICE_TURN` are empty) per
  ADR-0042/0046: the pilot intentionally skips TURN and uses the WebSocket
  transport for remote clients (and Genesys Audio Connector for telephony).
- The voice compose publishes **`8090/tcp` + `8091/tcp`** (WebSocket); the ephemeral
  UDP media ports chosen during WebRTC ICE are **not** published from the container.

Consequence: a remote browser can load `/webrtc.html` and complete the SDP
exchange, but the WebRTC audio stream will not connect. Use **`/ws.html`** for the
live remote path, or the batch one-shot path as a simple HTTP fallback.

## Testing WebRTC Media (Optional/Dev — Same-Subnet Only)

Pick one depending on the goal.

### Option A — Direct LAN test against a single node (quick check, no VIP)

Only viable if the test machine and the bridge share a directly reachable network
so ICE host candidates can connect. Point the browser at one node (bypassing the
VIP) so signaling and media target the same host:

- `http://vla-ai4cc-t01.prod.lan:8090/webrtc.html` (HTTP, not the TLS VIP).

If media still fails, it confirms the UDP ports are not reachable from the client
(expected with the current container port publishing) — move to Option B.

### Option B — Enable full WebRTC media (requires a change ticket)

One of:

1. **TURN relay:** stand up `coturn`, set `VOICE_TURN` /
   `VOICE_TURN_USERNAME` / `VOICE_TURN_CREDENTIAL` (and optionally `VOICE_STUN`) on
   the voice tier, and expose the media ports (publish a UDP range or run the
   bridge with host networking). This reverses the ADR-0042 pilot decision, so it
   needs an ADR update.
2. **Genesys Audio Connector (target for external voice):** route external media
   through Genesys per ADR-0042 / ADR-0040 instead of browser WebRTC.

Browser WebRTC then remains an internal/LAN convenience channel.

## Related Documents

- Signaling contract: [`../architecture/voice-runtime-http-contract.md`](../architecture/voice-runtime-http-contract.md)
- HAProxy edge (signaling vs media): [`../../deploy/haproxy/README.md`](../../deploy/haproxy/README.md)
- No-TURN pilot decision: [ADR-0042](../architecture/adrs/ADR-0042-no-turn-for-pilot-genesys-audio-connector-external-media.md)
- Genesys media plane: [ADR-0040](../architecture/adrs/ADR-0040-genesys-audio-connector-v2v-media-plane.md)
- WebRTC transport spike: [`../qa/webrtc-transport-spike.md`](../qa/webrtc-transport-spike.md)
- Pilot deployment + first-deploy runbook: [`deployment-eir-ai4cc-tst.md`](deployment-eir-ai4cc-tst.md), [`first-deploy-runbook.md`](first-deploy-runbook.md)
