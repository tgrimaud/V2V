# Adversarial Architecture Review — WebSocket As Primary V1 Live Voice Transport (ADR-0046)

**Date:** 2026-08-26
**Subject:** [ADR-0046](../adrs/ADR-0046-websocket-primary-live-voice-transport.md) — make WebSocket the primary V1 live voice transport and demote WebRTC to an optional same-subnet/dev path (supersedes [ADR-0033](../adrs/ADR-0033-webrtc-single-live-voice-transport.md)).
**Reviewer stance:** adversarial (stress-test, not validate).

## Verdict

**Proceed with conditions.** The decision is well-grounded and mostly *ratifies* a direction already accepted across ADR-0040/0042/0043 rather than opening a new bet: Genesys — the V1 production ingress — streams audio over `wss://`, external WebRTC is inoperable without TURN (deliberately unprovisioned), and the v0.6.0 pilot demonstrated WebRTC media cannot traverse the containerised bridges. Making WebSocket primary aligns the transport with both the contact-centre reality and the deployment reality, and reuses the ADR-0043 session factory rather than building a parallel stack. The conditions are about **quality of the direct-web path** (AEC/barge-in), **edge-routing correctness** (WebSocket upgrade over an `h2` TLS front), and **not letting the demoted WebRTC path rot**. None is a blocker to the decision itself; all must be tracked before any pilot GO claim for a live WebSocket call.

## Scorecard

| Dimension | Score /5 | Rationale |
|---|---:|---|
| NFR / SLA fitness | 3 | WS removes the TURN/UDP blocker and rides the existing edge; but there is **no measured mouth-to-ear for a live WS call yet** (ADR-0043 shipped the transport; the edge route TASK-INFRA-010 is unbuilt, so no end-to-end number exists). TCP head-of-line is an accepted but unmeasured risk. |
| SLA failure modes | 3 | Genesys leg gets barge-in/end-of-turn from Genesys events (ADR-0040), reducing runtime risk; but the direct-web WS path loses browser AEC → documented self-interruption risk (ADR-0025 pt7). Degraded modes for a dropped `wss` tunnel / HAProxy failover mid-call are not yet specified. |
| Modularity and boundaries | 4 | Strong: transport sits behind the ADR-0043 transport-agnostic session factory with a PCM16/16 kHz internal boundary and a pluggable control-signal seam. Backend conversation ownership (ADR-0001) untouched. Pipecat/Gradium orchestration unchanged. |
| External dependency replaceability | 4 | WS aligns to the AudioHook protocol shape, so Genesys Audio Connector becomes an adapter behind the same factory (Moderate→Easy). WebRTC remains available as an alternate transport adapter. No business-code coupling to the transport. |
| Evolvability and industrialization | 4 | Consolidating on one strategic live transport (web + Genesys) reduces the live surface to instrument/test/optimise, and turns Sprint-12 work into direct Sprint-13 capital. The `stdlib http.server` + edge-demux avoids an async-framework refactor. |
| **Overall** | **3.5** | Right strategic call, already half-decided by prior ADRs; provisional until a **measured live WS mouth-to-ear** and the **edge upgrade path** are proven, and the AEC gap on the direct-web path is owned. |

## Critical Risks

- **No end-to-end evidence for a live WebSocket call.** ADR-0043 delivered the transport and the pilot shows the *server* runs (`websocket=on:8091`), but the client never reached it (edge not routed). Until TASK-INFRA-010 + the `ws.js` fix land and one full `wss` turn is measured, the p95/TTFA for the *primary* transport is unknown. Do not claim a pilot GO for live WS voice on ADR-0046 alone.
- **WebSocket upgrade over an `h2` TLS front is unverified.** The voice VIP binds `alpn h2,http/1.1`. Browsers open WebSocket over HTTP/1.1, but this must be proven through *this* HAProxy config (upgrade tunneling, `timeout tunnel`, and no h2-only negotiation edge case), or the "just route it on 443" plan silently fails.
- **AEC/barge-in regression on the direct-web path.** Dropping WebRTC's native echo cancellation reintroduces the exact ADR-0025 pt7 failure without headphones. Acceptable for a headset pilot/demo and irrelevant on the Genesys leg, but a real limitation for any hands-free direct-web use — must be stated, not glossed.
- **Demoted-but-alive WebRTC drift.** A retained-but-secondary path tends to bit-rot (tests, deps: `aiortc`/`av`/`opencv`). Without a clear "optional/dev only" label and a CI guard, it will mislead future work or break unnoticed.

## Hard Questions

- What is the **measured** mouth-to-ear (p50/p95) and time-to-first-audio for a full live `wss` turn through the edge, versus the WebRTC 360 ms first-audio baseline (ADR-0033)? If materially worse, is it still acceptable for the pilot?
- Does the current HAProxy `voice_https` front actually tunnel a browser WebSocket upgrade, or does it need an explicit `Upgrade`/`Connection` handling + `timeout tunnel` change (i.e. is TASK-INFRA-010 a config add, not just an ACL)?
- Call affinity: the SDP-less WS session must pin to one bridge for its whole life. What is the stickiness mechanism, and what happens to an in-flight call on HAProxy reload / bridge drain (the TASK-INFRA-011 drain path)?
- For the **direct-web** channel specifically, do we accept "headset required" as a documented V1 constraint, or do we need a client-side AEC (WebAudio) fallback on the WS path?
- Do we keep WebRTC in the built image (opencv footprint, ADR-0022) or gate it out of the deployment image while keeping it for local dev?

## Architecture Challenges

- **Challenge: "WebSocket is strictly the right primary."** Mostly yes — but only because V1's live traffic is Genesys/telephony and off-subnet web. For a hypothetical hands-free, on-net web-first product, WebRTC's media stack would still win. The ADR correctly scopes WS as *V1* primary and keeps WebRTC as the on-net option; keep that scoping explicit so a future product pivot re-opens it via a new ADR rather than by accident. **Alternative retained:** WebRTC (optional, same-subnet/dev).
- **Challenge: "Edge-demux on 443 is enough."** It solves reachability, but not media quality (TCP HOL) nor AEC. The credible alternative for the *direct-web* path — not chosen — is a thin client-side AEC + jitter buffer over the WS PCM stream; note it as the mitigation if hands-free web becomes a requirement.
- **Challenge: single live transport = single point of design failure.** Consolidation is good for focus but means a WS-path defect affects both web and Genesys. Mitigate by keeping the control-signal seam and session factory transport-neutral (already the ADR-0043 design) so a transport bug is isolated from conversation logic.

## External Dependency Review

| Dependency | Current role | Replaceability | Concern | Recommendation |
|---|---|---|---|---|
| Genesys Cloud CX (Audio Connector) | Target V1 external media plane (`wss` AudioHook) | Moderate (adapter behind ADR-0043 factory) | Premium feature, ≤5 integrations, 15-min cap, PCMU/L16 (ADR-0040) | Validate via the TASK-WEB-025 spike before Sprint-13 build |
| HAProxy (voice VIP edge) | TLS edge + LB; must now carry `wss` upgrade | Easy (config) but **platform-managed** | `h2` ALPN + upgrade tunneling unproven; nodes not owned by these playbooks | TASK-INFRA-010 + confirm with the platform team |
| Gradium STT/TTS | Server↔provider WS (unchanged) | Easy (ports) | None from this decision | No action |
| aiortc/av/opencv (WebRTC) | Now optional/dev transport | Easy to gate | Footprint + drift if unlabelled | Mark optional/dev; consider excluding from the deploy image |

## NFR / SLA Gaps

- **Missing:** a measured live-WS mouth-to-ear + TTFA (the primary transport has no end-to-end number yet).
- **Missing:** a specified degraded mode for a `wss` tunnel drop / HAProxy failover mid-call, and the call-affinity/stickiness contract.
- **Missing:** an explicit V1 statement on direct-web AEC ("headset required" vs client-side AEC fallback).
- **Present/good:** transport behind a session factory (testable, swappable); Genesys-event ownership of barge-in on the CC leg; no TURN/UDP ops burden.

## Recommended Changes

1. **Must fix before production (pilot GO for live WS voice):**
   - Land TASK-INFRA-010 (HAProxy `wss` upgrade routing + `timeout tunnel` + affinity) and the `ws.js` same-origin `:443` fix; **measure one full live `wss` turn** (p95 mouth-to-ear, TTFA) and record it against the ADR-0029 gate.
   - Verify WebSocket upgrade actually tunnels through the `h2,http/1.1` front with the platform team.
2. **Should fix before pilot:**
   - Document the direct-web AEC constraint (headset) or add a client-side AEC fallback on the WS path.
   - Specify call affinity + mid-call failover/drain behaviour for WS sessions (tie into TASK-INFRA-011 drain).
   - Label WebRTC "optional/dev only" in code + docs and add a light CI guard so it doesn't rot; decide image inclusion.
3. **Can defer safely:**
   - Client-side jitter buffer tuning for TCP HOL on the WS path.
   - Revisit WebRTC's status only if a hands-free on-net web-first product requirement emerges (new ADR).
