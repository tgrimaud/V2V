# ADR-0046: WebSocket Is The Primary V1 Live Voice Transport (WebRTC Demoted To Optional Same-Subnet/Dev)

## Status

Accepted (2026-08-26, user-directed). **Supersedes**
[ADR-0033](ADR-0033-webrtc-single-live-voice-transport.md) (WebRTC as the single live
transport). **Refines** the client-facing transport emphasis of
[ADR-0022](ADR-0022-webrtc-transport-for-streaming-voice-loop.md) and
[ADR-0002](ADR-0002-pipecat-gradium-target-voice-path.md) (Pipecat/Gradium orchestration
unchanged). **Builds on** [ADR-0040](ADR-0040-genesys-audio-connector-v2v-media-plane.md),
[ADR-0042](ADR-0042-no-turn-for-pilot-genesys-audio-connector-external-media.md), and
[ADR-0043](ADR-0043-interim-websocket-audio-transport-genesys-ready.md). **Followed by**
[ADR-0047](ADR-0047-single-async-http-websocket-server-one-port.md) (unify onto a single async
HTTP+WebSocket server on one port — removes the WS edge special-case + platform dependency and
lifts the one-call-per-bridge cap; TASK-WEB-037 is the interim bridge, ADR-0047 the
destination). Adversarial review:
`docs/architecture/reviews/websocket-primary-transport-adversarial-review-2026-08-26.md`.

## Context

[ADR-0033](ADR-0033-webrtc-single-live-voice-transport.md) declared **WebRTC the single
live (customer-facing) voice transport** for the web channel and **rejected** a
browser-facing WebSocket, on two grounds that were correct *for a same-subnet developer web
widget*: WebRTC gives browser-native **echo cancellation, noise suppression, jitter
buffering and Opus** for free (the AEC that ADR-0025 barge-in depends on), and ≈ 360 ms
time-to-first-audio. ADR-0033 explicitly scoped itself **web-only** and left
telephony/Genesys media out of scope.

Three things have since changed the balance decisively:

1. **The V1 production ingress is Genesys-mediated, and Genesys speaks WebSocket, not
   WebRTC.** `CLAUDE.md` fixes Genesys Cloud CX as the contact-center system of record for
   call ingestion, and [ADR-0040](ADR-0040-genesys-audio-connector-v2v-media-plane.md) fixes
   **Genesys Audio Connector** (the bidirectional feature of the AudioHook protocol) as the
   target V2V media plane — a Genesys-initiated `wss://` audio stream. WebRTC is the transport
   of the Genesys *agent softphone*, never the transport by which Genesys streams call audio
   to an external bot. So the real customer-call media plane is **WebSocket**.

2. **External-browser WebRTC audio does not work without TURN, and TURN was deliberately not
   provisioned.** [ADR-0042](ADR-0042-no-turn-for-pilot-genesys-audio-connector-external-media.md)
   already found that with `VOICE_STUN`/`VOICE_TURN` empty the bridge advertises only its
   private host ICE candidate (signalling succeeds, media is silent off-subnet) and chose **not**
   to stand up a public TURN relay, precisely because the external media plane is Genesys wss.
   [ADR-0043](ADR-0043-interim-websocket-audio-transport-genesys-ready.md) then delivered an
   interim **AudioHook-shaped WebSocket** transport (Sprint 12, TASK-WEB-028) as **reusable
   capital** toward Genesys Audio Connector: a transport-agnostic session factory, a PCM16/16 kHz
   internal boundary, and a pluggable control-signal seam.

3. **Pilot evidence (v0.6.0, 2026-08-26) confirms WebRTC is inoperable in the deployed
   topology.** On the containerised bridges the compose publishes only `8090/tcp`; `aiortc`
   inside the container gathers only the container-internal `10.89.x` host candidate, no UDP
   media path is published, and no TURN exists → ICE goes `connecting → closed`, no audio
   reaches the pipeline, and the caller hears nothing (page loads, signalling + backend warm-up
   succeed, then silence). The WebSocket path (server on `:8091`, AudioHook-shaped) is the one
   *designed* to reach external clients over TCP through the HTTPS edge, but its edge routing
   (TASK-INFRA-010) had not yet been wired.

Net: WebRTC is **neither** the transport Genesys uses **nor** operable off-subnet without
TURN/host-networking; WebSocket is **both** the Genesys-aligned transport **and** the
edge/NAT-friendly external-reach path. ADR-0033's "single live transport = WebRTC" premise no
longer holds once V1 leaves the same-subnet dev bench.

## Decision

1. **WebSocket is the primary V1 live voice transport.** The AudioHook-shaped `wss://` path
   (JSON control frames + binary PCM16/16 kHz audio, ADR-0043) is the reference live transport
   for **both** the external web channel **and** the Genesys Audio Connector media plane
   (ADR-0040). New live-voice runtime work targets the WebSocket path via the transport-agnostic
   session factory extracted in ADR-0043.

2. **WebRTC (ADR-0022) is demoted to an optional, same-subnet/dev-only live transport.** It is
   retained for local low-latency development and the on-net browser experience, where its
   native AEC/noise-suppression/jitter/Opus are a genuine advantage. It is **not** on the V1
   external/pilot critical path, and any off-subnet use requires its own TURN/host-networking
   provisioning ADR first. WebRTC code is **demoted, not deleted** (it carries the ADR-0022/0025
   barge-in mechanics and remains the on-net low-latency option).

3. **ADR-0033 is superseded.** WebRTC is no longer "the single live transport", and a
   browser-facing WebSocket is no longer rejected — it is the reference external transport.

4. **Unchanged:** the server↔provider WebSocket (voice-agent ↔ Gradium STT/TTS), the Pipecat +
   Gradium orchestration (ADR-0002), the modular cascade (ADR-0012), and the batch HTTP `/turn`
   path as **offline/tests only** (ADR-0033 point 4 preserved).

5. **Delivery consequence:** finishing the WebSocket edge moves **onto the V1 critical path**.
   TASK-INFRA-010 (HAProxy `wss` upgrade routing on the voice VIP → `bridges:8091`, long tunnel
   timeout, call affinity) plus the one-line `ws.js` fix to use same-origin `wss://<host>/` on
   :443 (instead of a hard-coded `:8091`) is the enabler for **both** external browser testing
   **and** the Sprint-13 Genesys Audio Connector. Tracked by **TASK-WEB-037**.

## Consequences

**Positive**

- One strategic live transport that is **Genesys-native** and **edge/NAT-friendly**: TCP
  through the existing HAProxy TLS edge, no coturn/TURN, no UDP media publishing, no ICE.
- The Sprint-12 WebSocket transport (ADR-0043) + session factory become the **direct
  substrate** for ADR-0040 Genesys Audio Connector — no throwaway, no parallel stack.
- Removes the pilot blocker's root cause (WebRTC container media gap + missing TURN) from the
  V1 critical path; external reachability becomes an edge-routing task, not a media-plane rebuild.

**Negative / risks**

- The **direct-web widget loses browser-native AEC/noise/jitter/Opus** on the WS path, so
  barge-in without headphones can self-interrupt (ADR-0025 point 7). Mitigation: the WS
  control-signal seam already carries energy/amplitude detectors; pilot/demo uses headphones;
  and on the Genesys leg, barge-in/end-of-turn/playback come from **Genesys events** (ADR-0040),
  not the browser media stack.
- **TCP head-of-line blocking** and weaker jitter handling than WebRTC (accepted in ADR-0043).
- WebRTC code stays in the tree as the optional path → maintenance/test cost; it must be clearly
  labelled optional/dev to prevent drift and false "primary path" assumptions.

**Neutral**

- Pipecat + Gradium orchestration (ADR-0002) and the modular STT/RAG/LLM/TTS cascade (ADR-0012)
  are unchanged — only the **client-facing transport emphasis** changes. Provider agnosticism is
  preserved: the transport sits behind the ADR-0043 session factory.

## Alternatives Considered

- **Keep WebRTC as the single live transport (status quo ADR-0033) and provision TURN/coturn for
  external reach:** rejected — it stands up public UDP-relay infrastructure (coturn, public
  IP/DNS, relay port range, credentials, its own SPOF/ops) for a transport **Genesys does not
  use**. ADR-0042 already rejected TURN for the pilot on exactly this ground.
- **Run WebRTC and WebSocket as co-equal primary live transports:** rejected — doubles the live
  surface to instrument, test and optimise (the very duplication ADR-0033 point 1 sought to
  avoid) for a web-only benefit, while Genesys still mandates WebSocket. WebRTC as an *optional*
  path (not co-equal-primary) keeps the live surface single.
- **Unify HTTP + WebSocket onto one in-process port by replacing the stdlib `http.server` with an
  async framework (FastAPI/aiohttp/uvicorn):** rejected here — an application refactor contrary to
  the stdlib choice of ADR-0022; the HAProxy edge-demux (`:443` → internal `:8091`) achieves a
  single **public** port without it. Left open as a future ADR only if the runtime needs a unified
  async server for unrelated reasons.
- **Drop WebRTC from the tree now:** rejected — it is the validated on-net low-latency dev/demo
  path and carries the ADR-0022/0025 barge-in learnings. Demote, do not delete.

## Related Documents

- [ADR-0033 — WebRTC single live transport](ADR-0033-webrtc-single-live-voice-transport.md) (**superseded by this ADR**)
- [ADR-0022 — WebRTC transport for the streaming voice loop](ADR-0022-webrtc-transport-for-streaming-voice-loop.md) (refined: WebRTC now optional/dev)
- [ADR-0002 — Pipecat + Gradium target voice path](ADR-0002-pipecat-gradium-target-voice-path.md)
- [ADR-0012 — Modular voice pipeline over realtime API](ADR-0012-modular-voice-pipeline-over-realtime-api.md)
- [ADR-0025 — Barge-in native interruption](ADR-0025-barge-in-native-interruption.md)
- [ADR-0040 — Genesys Audio Connector V2V media plane](ADR-0040-genesys-audio-connector-v2v-media-plane.md)
- [ADR-0042 — No TURN for the pilot](ADR-0042-no-turn-for-pilot-genesys-audio-connector-external-media.md)
- [ADR-0043 — Interim WebSocket audio transport, Genesys-ready](ADR-0043-interim-websocket-audio-transport-genesys-ready.md)
- TASK-WEB-037 (transport consolidation + `ws.js` same-origin fix), TASK-INFRA-010 (HAProxy `wss` edge routing), TASK-WEB-028 (interim WS transport), TASK-WEB-025 (Genesys Audio Connector spike)
- `docs/architecture/reviews/websocket-primary-transport-adversarial-review-2026-08-26.md`
