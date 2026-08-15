# ADR-0042: No TURN For The Pilot — External Voice Media Goes Through Genesys Audio Connector

## Status

Accepted (2026-08-14)

> Update (2026-08-15): the interim WebSocket audio path (Decision point 4) is now a
> **committed decision**, not a conditional lever — a concrete need for an external
> browser voice demo before Genesys Audio Connector has been confirmed. It becomes the
> content of the next sprint (Sprint 12) and is specified by ADR-0043. "No TURN for the
> pilot" (points 1–3) is unchanged: the external path stays a client→server TCP/TLS
> WebSocket through the existing HAProxy edge, so no STUN/TURN is provisioned.

> Refines ADR-0033 (WebRTC as the single live web voice transport) and ADR-0040
> (Genesys Audio Connector as the target V2V media plane). It does not change runtime
> code; it fixes the media-plane strategy for the pilot so we do not provision TURN.

## Context

Pilot validation on eir-ai4cc-tst proved the full server-side voice journey works
end to end **between mesh VMs** and through the HTTPS edge:
signalling (HTTPS/TLS via HAProxy) → voice bridge → STT (Gradium) → backend RAG+LLM →
TTS (Gradium) → answer audio. A `POST /api/voice/turn` returned `X-Answer-Outcome:
success` with a grounded billing answer both directly against a bridge and through the
voice VIP `.10:443`.

What does **not** work is audio for a client **outside** the `192.168.0.0/24` subnet.
WebRTC uses two independent planes:

- **Signalling** (HTTPS/TCP): loads the UI and exchanges the SDP offer/answer — works
  through HAProxy already.
- **Media** (SRTP/RTP over UDP): a direct peer path negotiated by ICE. The bridge has
  `VOICE_STUN`/`VOICE_TURN` empty, so it only advertises its **host** candidate (a
  private `192.168.0.x` address). A same-subnet VM can reach it (audio OK — validated);
  an external browser cannot, so ICE finds no usable media path and the call is silent
  even though the page looks "connected".

Making external WebRTC audio work would require provisioning **STUN/TURN** (a public
relay: coturn, public IP/DNS, `3478` UDP/TCP + `5349` TLS + a UDP relay port range,
credentials). For the pilot this infrastructure cost is **not justified**: the target
contact-centre integration already routes external voice through **Genesys Audio
Connector** (ADR-0040), whose media plane is a Genesys-initiated `wss://` AudioHook
stream — it does **not** rely on browser-to-bridge WebRTC or on TURN at all.

## Decision

1. **Do not provision STUN/TURN for the pilot.** `VOICE_STUN`/`VOICE_TURN` stay empty.
2. **Direct WebRTC (ADR-0033) is scoped to same-subnet / on-VM use** — internal
   validation, demos and dev — where host ICE candidates suffice. It is not the external
   customer entry path for the pilot.
3. **The external voice media plane is Genesys Audio Connector** (ADR-0040): a
   bidirectional AudioHook `wss://` stream that Genesys initiates to our runtime. Because
   Genesys reaches our endpoint over TLS/WebSocket (server-to-server, no browser NAT
   traversal), **no TURN relay is needed**.
4. **Interim WebSocket audio path — now committed (Sprint 12, ADR-0043).** The external
   browser voice path is a **WebSocket audio transport** to the bridge (TCP/TLS,
   traverses the same HAProxy edge that already works) — chosen over standing up TURN.
   Same NAT-traversal property as Genesys Audio Connector (a client→server TLS
   connection carries the audio; no UDP peer-to-peer, no ICE, no STUN/TURN). It remains
   an interim transport, not a second long-lived one: it is superseded by Genesys Audio
   Connector (ADR-0040) for the target contact-centre path, and differs from it in
   application protocol (our own PCM framing vs Genesys AudioHook) and in using TCP for
   real-time media (jitter/head-of-line trade-off vs WebRTC/UDP on lossy links).

The Java backend remains the source of truth for conversation, RAG, guardrails,
escalation and memory (ADR-0001); Genesys stays the contact-centre system of record
(ADR-0020). This ADR only fixes how customer **audio** reaches the runtime for the pilot.

## Consequences

- No coturn / public relay to deploy, secure, credential-rotate or budget for the pilot.
- The pilot's externally reachable voice journey is delivered via the Genesys Audio
  Connector spike (ADR-0040), not via public WebRTC; roadmap and demos must not promise
  "open the web URL and talk from anywhere" until either Audio Connector or the interim
  WebSocket path is in place.
- Barge-in / end-of-turn on the external path defer to Genesys protocol events
  (ADR-0040), not the energy/amplitude detectors, which stay for the direct WebRTC/dev
  path (ADR-0025, ADR-0033).
- If a genuine public-WebRTC need reappears later, TURN provisioning can be revisited as
  a separate decision; it is deliberately out of scope now.
- Documentation (deployment guide, HAProxy README) should state that external browser
  audio is not enabled via WebRTC on the pilot and point to this ADR.

## Alternatives Considered

- **Provision STUN/TURN (coturn) for public WebRTC audio:** rejected for the pilot —
  real infra cost (public IP/DNS, UDP relay range, credentials, security) for a path the
  target architecture replaces with Genesys Audio Connector.
- **STUN only (no TURN):** rejected — insufficient behind corporate symmetric NAT /
  closed UDP; would work inconsistently and still needs a public reflexive path.
- **Keep pushing browser WebRTC as the external entry now:** rejected — silent-audio
  trap for external users; signalling succeeds while media fails.
- **Stand up the WebSocket audio path immediately:** ~~deferred~~ **selected** (update
  2026-08-15) — a concrete pre-Genesys external need was confirmed; specified by ADR-0043
  and scheduled as Sprint 12. Preferred over TURN because it reuses the working TLS edge
  and carries the NAT-traversal property of the target Genesys path.

## Related Documents

- `docs/architecture/adrs/ADR-0033-webrtc-single-live-voice-transport.md`
- `docs/architecture/adrs/ADR-0040-genesys-audio-connector-v2v-media-plane.md`
- `docs/architecture/adrs/ADR-0020-genesys-handoff-v1-full-audio-connector-optional.md`
- `docs/architecture/adrs/ADR-0025-barge-in-native-interruption.md`
- `docs/architecture/adrs/ADR-0001-java-backend-owns-conversation-domain.md`
- `docs/operations/deployment-eir-ai4cc-tst.md`
- `deploy/haproxy/README.md`
