# ADR-0049: Genesys Audio Connector Sprint 13 Delivery Shape (Spike-Gated)

## Status

Proposed (2026-08-27). **Gated by** [OQ-006](../../../product-backlog/open-questions/v1-open-questions.md#oq-006---genesys-handoff-integration-shape)
and by the **TASK-WEB-025** feasibility spike go/no-go — this ADR records the *target
delivery shape* for Sprint 13 and marks exactly what the spike must resolve before any
commitment. Moves to **Accepted** only on a spike **GO** + OQ-006 answers; parked (or
Superseded) on **NO-GO**. **Refines** [ADR-0040](ADR-0040-genesys-audio-connector-v2v-media-plane.md)
(the 3-plane split). **Builds on** [ADR-0046](ADR-0046-websocket-primary-live-voice-transport.md),
[ADR-0047](ADR-0047-single-async-http-websocket-server-one-port.md),
[ADR-0043](ADR-0043-interim-websocket-audio-transport-genesys-ready.md),
[ADR-0019](ADR-0019-escalation-rules-and-handoff-contract.md),
[ADR-0020](ADR-0020-genesys-handoff-v1-full-audio-connector-optional.md),
[ADR-0009](ADR-0009-independent-channel-adapters-shared-java-backend.md),
[ADR-0029](ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md),
[ADR-0025](ADR-0025-barge-in-native-interruption.md), [ADR-0001](ADR-0001-java-backend-owns-conversation-domain.md).
Source review: `docs/architecture/reviews/genesys-audio-connector-adversarial-review-2026-08-07.md`
(Must-fix R1–R6). Sprint: `product-backlog/sprints/sprint-13-genesys-audio-connector.md`.

## Context

ADR-0040 fixed the *target* Genesys integration as a three-plane split (media / control /
context) with **Audio Connector** (the bidirectional AudioHook feature) as the V2V media
plane, but explicitly **not implemented** and deferred to Sprint 13 under OQ-006. The
2026-08-07 adversarial review scored that target **2.2/5** and said *"proceed with
conditions — as a bounded, measured feasibility spike, NOT as V1 core"*, raising six
Must-fix risks (R1–R6): latency deficit, the 15-minute cap, absent degraded modes, dual
barge-in/end-of-turn logic, an unproven handoff mapping, and unquantified concurrency.

Two things changed the runtime foundation **after** ADR-0040:

- **ADR-0046** made **WebSocket the primary V1 live transport** (web + Genesys), demoting
  WebRTC to optional same-subnet/dev.
- **ADR-0047** unified the runtime onto a **single async HTTP+WebSocket server on one port**
  (delivered by TASK-WEB-038, shipped v0.7.0), reusing the **ADR-0043 transport-agnostic
  session factory** and a **PCM16/16 kHz internal boundary**.

Net: the Audio Connector media plane is now deliverable as **one more transport adapter** on
an async server that already exists — not a parallel stack. Sprint 13 needs a decision that
(a) fixes this delivery shape, (b) settles the R1–R6 conditions into concrete ticket-level
commitments, and (c) is honest that several sub-choices are **spike-to-confirm**, not
assumed.

## Decision

Deliver the Genesys integration in Sprint 13 as the following shape, **gated by the
TASK-WEB-025 go/no-go**:

1. **Media plane = a transport adapter, not a stack.** The Audio Connector AudioHook
   `wss://` endpoint is exposed on the **ADR-0047 single async HTTP+WebSocket server**,
   built via the **ADR-0043 session factory**. Codec conversion (**PCMU/µ-law ↔ PCM16**,
   **L16 ↔ PCM16**) lives **inside the transport adapter**; the shared session core stays
   PCM16/16 kHz. One bidirectional stream per session, IVR channel (TASK-WEB-041).

2. **Control/routing plane stays in Genesys Architect + Platform API.** A Genesys Architect
   **Call Audio Connector** action forks + pauses the flow to our endpoint; on session end
   the flow resumes and routes to the billing advisor queue. Our runtime never transfers the
   call itself (TASK-INFRA-012).

3. **Context/handoff plane stays backend-owned, transported by reference.** The recommended
   target is **`handoff_id` + `customer_reference` carried through Architect variables /
   conversation attributes, with the full audited `EscalationHandoff` (ADR-0019) fetched
   from the backend on demand** — avoiding Architect variable size limits (R5). Inline
   transport is a documented fallback only if the spike shows a minimal subset fits with a
   safe margin (TASK-BE-036 + TASK-BE-037).

4. **Barge-in / end-of-turn ownership is per path.** On the **Genesys path** the native
   Genesys events (`barge-in`, `playback-started`/`playback-completed`, `BotTurnResponse`)
   are authoritative and the in-house energy/amplitude detectors (ADR-0025) are **disabled**;
   the in-house detectors remain the mechanism for the **WS/WebRTC dev path** only (R4,
   TASK-WEB-042).

5. **Degraded modes fail safe to the advisor queue.** Endpoint down/slow/timeout, session
   drop, 15-minute-cap timeout, and transcode failure each end the streaming session cleanly
   so Architect resumes and routes to a human — never dead air (R3, TASK-WEB-044 +
   TASK-INFRA-012). Backend conversation memory is preserved (ADR-0044 posture).

6. **The Genesys path stays a measured spike off the V1 critical path until the latency gate
   is re-scored PASS.** The full round trip is decomposed into per-leg slices under **one
   trace** (Genesys `conversationId` → OpenTelemetry) and re-scored against **ADR-0029**
   (mouth-to-ear p95 ≤ 1.5 s). A minimal concurrency ceiling + backpressure is measured on a
   1-vCPU-class runtime, and the premium ≤5-integrations/org budget is tracked (R1 + R6,
   TASK-WEB-043).

7. **The Genesys boundary is fixed (ADR-0001).** No RAG, billing reasoning, guardrails,
   escalation policy, handoff content, or conversation memory moves into Genesys. Genesys is
   the contact-center system of record; the Java backend is the conversation brain. Genesys
   is one channel behind the normalized envelope (ADR-0009): `channel`, `external_session_id`,
   `message_id`, `idempotency_key`, `reply_mode`, `escalation_context` (TASK-BE-037).

### What the spike (TASK-WEB-025) must resolve before commitment

This ADR is Proposed precisely because the following are **not assumed** — they are the
gate's outputs (also OQ-006 decision items):

- **R1 — Isolated Genesys-leg latency** and the ADR-0029 re-score (go/no-go for the media
  plane on the critical path).
- **R2 — 15-minute cap** vs the worst-case billing journey → keep-as-is, checkpoint/resume,
  or call-back.
- **R3 — At least one degraded mode** observed (Architect behaviour on endpoint-down).
- **R4 — Confirmation of the Genesys native events** and the per-path ownership rule.
- **R5 — Architect variable/attribute size + type limits** → confirm `handoff_id` + fetch vs
  inline.
- **R6 — A minimal concurrency ceiling** on a 1-vCPU-class runtime + the premium
  ≤5-integrations impact.
- **Codec (PCMU vs L16)** end to end + the transcode budget.
- **Data residency / egress** for the PII audio leaving the Genesys cloud to the runtime VMs.

## Consequences

- Sprint 13 is **gate-first**: the spike commits or defers everything else. A **NO-GO** parks
  this ADR at Proposed with the rationale, and the follow-on tickets carry forward — the
  backend conversation engine and the web/WS channels are unaffected.
- The Sprint-12 WebSocket transport + ADR-0043 session factory + ADR-0047 async server are
  **reused, not duplicated** — Genesys becomes a transport-adapter swap.
- The handoff stays **backend-owned and auditable** even under Genesys variable limits, which
  keeps escalation policy and billing evidence centralized (ADR-0001/0019).
- Latency honesty is preserved: the Genesys path is a **measured spike** until the gate is
  re-scored, so no premium provider silently degrades the (already-FAIL, TASK-WEB-039) gate.
- A per-path control-signal rule prevents the runtime from fighting the Genesys protocol
  (self-interruptions / lost turns).

## Alternatives Considered

- **Ship the Audio Connector media plane as V1 core now (no spike gate):** rejected — the
  ADR-0029 gate is already FAIL and the Genesys leg is unmeasured; the adversarial review
  explicitly required a measured spike first (R1).
- **Carry the full `EscalationHandoff` inline in Architect variables:** rejected as the
  default — variable/attribute size limits risk truncating summary + citations (R5); kept
  only as a spike-validated fallback for a minimal subset.
- **Keep the in-house barge-in/end-of-turn detectors active on the Genesys path too:**
  rejected — duplicates and fights the Genesys native events (R4).
- **Build a bespoke Genesys media stack separate from the WS transport:** rejected — throws
  away the ADR-0043/0046/0047 capital; the async server + session factory are the intended
  substrate.
- **Add Twilio/SIP telephony as a second pilot entry in the same sprint:** deferred — one
  pilot entry is chosen by the spike (the review's "pick one"); a second media profile
  doubles the barge-in/latency surface to test.
- **Let Genesys own routing decisions / a Genesys-native voicebot:** rejected — contradicts
  ADR-0001/0040 (the backend is the conversation brain).

## Related Documents

- [ADR-0040 — Genesys Audio Connector V2V media plane](ADR-0040-genesys-audio-connector-v2v-media-plane.md) (refined by this ADR)
- [ADR-0046 — WebSocket primary live voice transport](ADR-0046-websocket-primary-live-voice-transport.md)
- [ADR-0047 — Single async HTTP+WebSocket server on one port](ADR-0047-single-async-http-websocket-server-one-port.md)
- [ADR-0043 — Interim WebSocket audio transport, Genesys-ready](ADR-0043-interim-websocket-audio-transport-genesys-ready.md)
- [ADR-0019 — Escalation rules and handoff contract](ADR-0019-escalation-rules-and-handoff-contract.md)
- [ADR-0020 — Genesys handoff in V1, full Audio Connector optional](ADR-0020-genesys-handoff-v1-full-audio-connector-optional.md)
- [ADR-0009 — Independent channel adapters, shared Java backend](ADR-0009-independent-channel-adapters-shared-java-backend.md)
- [ADR-0029 — Pilot latency criterion](ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md)
- [ADR-0025 — Barge-in native interruption](ADR-0025-barge-in-native-interruption.md)
- [ADR-0001 — Java backend owns the conversation domain](ADR-0001-java-backend-owns-conversation-domain.md)
- `docs/architecture/reviews/genesys-audio-connector-adversarial-review-2026-08-07.md` (R1–R6)
- `product-backlog/sprints/sprint-13-genesys-audio-connector.md`
- `product-backlog/open-questions/v1-open-questions.md` (OQ-006)
- Tickets: TASK-WEB-025 (gate), TASK-WEB-041/042/043/044, TASK-BE-036/035, TASK-INFRA-012
