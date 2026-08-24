# Pilot Voice Access — Entry Points And WebRTC Status

## Objective

Give operations and QA a single place to answer "how do I reach the voice bot on
the pilot, and what actually works today?". It documents the two browser entry
points (batch one-shot and streaming WebRTC), the deployment topology behind the
voice VIP, and the current WebRTC media limitation.

This is an access/runbook note. The signaling contract itself lives in
[`../architecture/voice-runtime-http-contract.md`](../architecture/voice-runtime-http-contract.md);
the media-plane decision lives in
[`../architecture/adrs/ADR-0042-no-turn-for-pilot-genesys-audio-connector-external-media.md`](../architecture/adrs/ADR-0042-no-turn-for-pilot-genesys-audio-connector-external-media.md).

## Scope

- Environment: pilot `eir-ai4cc-tst` — voice bridges `vla-ai4cc-t01/t02.prod.lan`
  (`.103/.104`), one bridge per VM, behind the voice VIP
  `https://vip-ai4cc-voice-t01.prod.lan/` (`.10`, HAProxy TLS edge).
- The voice bridge image binds `0.0.0.0:8090`; HAProxy terminates TLS on `:443`
  and load-balances to `vla-t01/t02:8090`.

## Entry Points

The voice bridge serves both clients from the same HTTP server. The root path is
the batch client; the WebRTC client is a separate static page.

| Channel | Browser URL | Signaling / API endpoint | Media |
|---------|-------------|--------------------------|-------|
| Batch one-shot (validated) | `https://vip-ai4cc-voice-t01.prod.lan/` (serves `index.html`) | `POST /api/voice/turn` (PCM16 in → full-answer WAV out) | HTTP response body over HTTPS (through HAProxy) |
| Streaming WebRTC | `https://vip-ai4cc-voice-t01.prod.lan/webrtc.html` | `POST /api/voice/webrtc/offer` (SDP offer → SDP answer) | RTP/SRTP over **UDP**, peer-to-peer with the answering bridge — **not** through HAProxy |

Notes:

- `GET /` returns `index.html` (batch). Any other path is served as a static file,
  so the WebRTC UI is reached at **`/webrtc.html`** (paired with `webrtc.js`).
- Other endpoints on the same server: `POST /api/voice/stt`, `POST /api/voice/tts`,
  and `GET /api/voice/openapi.yaml`.

## What Works Today

- **Batch one-shot is the working end-to-end path.** Open the VIP root, record a
  question, and the full multi-sentence answer is transcribed, answered and spoken
  back in one HTTP turn (validated on `v0.5.2`, BUG-015).
- **WebRTC signaling is live** on the bridges: the image ships the
  `pipecat-ai[webrtc]` runtime and starts with `--webrtc auto`, so
  `POST /api/voice/webrtc/offer` negotiates an SDP answer.

Verify signaling is active on a node (out-of-band, not through the VIP):

```bash
# 502 webrtc_negotiation_failed = signaling is ON (empty offer is invalid, as expected).
# 503 webrtc_unavailable        = signaling is OFF (webrtc extra missing / --webrtc off).
ssh -i ~/.ssh/id_itsf grimaud@vla-ai4cc-t01.prod.lan \
  'IP=$(hostname -I | awk "{print \$1}"); \
   curl -s -m 6 -X POST -H "Content-Type: application/json" -d "{}" \
     -w "\nHTTP %{http_code}\n" http://$IP:8090/api/voice/webrtc/offer'
```

## Current Limitation — WebRTC Media Does Not Establish For Remote Clients

Signaling succeeding does **not** mean audio flows. On the pilot:

- **HAProxy carries signaling + UI only** (HTTPS). WebRTC media is UDP
  peer-to-peer and never traverses HAProxy — see
  [`../../deploy/haproxy/README.md`](../../deploy/haproxy/README.md).
- **No STUN/TURN** is configured (`VOICE_STUN` / `VOICE_TURN` are empty) per
  ADR-0042: the pilot intentionally skips TURN and routes external voice media
  through the **Genesys Audio Connector** instead.
- The voice compose publishes **`8090/tcp` only**; the ephemeral UDP media ports
  chosen during ICE are not published from the container.

Consequence: a remote browser can load `/webrtc.html` and complete the SDP
exchange, but the audio stream will not connect. The batch one-shot path is the
supported browser test until media is enabled.

## Testing WebRTC Media (Options)

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
