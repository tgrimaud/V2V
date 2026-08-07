# Adversarial Architecture Review — Genesys Audio Connector As The V2V Media Plane

- **Date:** 2026-08-07
- **Branch:** `task/TASK-DOC-006-genesys-audio-connector-media-plane` (off `feat/restart-from-scratch`)
- **Subject:** The target Genesys integration for Voice2Voice — media plane via the
  **Audio Connector** feature of the AudioHook protocol, plus escalation handoff.
- **Decisions reviewed:** ADR-0040 (Genesys Audio Connector as the V2V media plane),
  ADR-0020 (Genesys handoff, full routing optional), ADR-0019 (escalation rules and
  handoff contract). Related: ADR-0001, ADR-0009, ADR-0025, ADR-0029, ADR-0033.
- **Skill applied:** `adversarial-architecture-review` (scorecard /5).
- **Implementation reality at review time:** **NOT IMPLEMENTED.** No Genesys adapter,
  no Audio Connector WebSocket server, no Architect flow exists. Full Genesys voice
  routing is deferred (Sprint 13, gated by OQ-006). This review stress-tests the
  *target decision*, not shipped code.
- **Sources:** Genesys AudioHook introduction, AudioHook Protocol Reference, Audio
  Connector overview (Genesys Cloud developer/resource center).

---

## Verdict

**Proceed with conditions — as a bounded, *measured* feasibility spike, NOT as V1
core.** The architecture decision itself (three-plane split, backend owns the
conversation brain, Genesys is a channel/contact-center adapter) is **sound and
well-scoped**. But the Audio Connector media path **mechanically worsens** a latency
budget the project **already fails** on the shorter direct WebRTC path (mouth-to-ear
p95 ≈ 2.1 s vs ADR-0029 gate = 1.5 s); it introduces a constrained premium provider;
and **none** of its failure modes are currently designed or tested. Keeping full voice
routing optional and deferred (ADR-0020, Sprint 13, OQ-006) is the correct posture —
this review confirms it and hardens the conditions.

---

## Scorecard

| Dimension | Score /5 | Rationale |
|---|---:|---|
| NFR / SLA fitness | 2 | The ADR-0029 mouth-to-ear gate (1.5 s) is already FAIL (~2.1 s) on the shortest path. A Genesys cloud round trip + PCMU/L16 transcoding + an extra WebSocket hop can only add latency, and the Genesys leg is **unmeasured**. The 15-minute call cap is unvalidated against a billing journey with waits. |
| SLA failure modes | 2 | Endpoint down, session drop, Genesys unreachable, transcoding failure, 15-minute timeout mid-call: no degraded mode defined. Only upside: the Architect action **resumes the flow** at session end → a natural fallback hook, but it is unspecified. |
| Modularity and boundaries | 3 | **Strongest axis.** Clean three-plane split; backend owns decisions/RAG/guardrails; Genesys sits behind the normalized channel envelope (ADR-0009). But the `EscalationHandoff` (ADR-0019) ↔ Architect-variable/conversation-attribute mapping is **unproven** and no adapter code exists. |
| External dependency replaceability | 3 | The **brain stays replaceable** (in-house engine). But the media plane is a **bespoke AudioHook `wss` server** specific to Genesys (proprietary, premium): media replaceability = Moderate→Hard, brain = Easy. |
| Evolvability and industrialization | 2 | Premium app, **≤5 integrations/org**, **one bidirectional stream/session**, LB VMs are **1 vCPU**, no load test for this path, no per-leg SLO decomposition for the Genesys hops. |
| **Overall** | **2.2** | Credible as a spike; **not** an industrializable brick without degraded-mode contracts, per-leg measurement, and a concurrency/load test. |

Scoring note: no dimension exceeds 3 because there is no code, no measurement, and no
failure-mode testing yet — per the skill's strict rule, 4+ requires evidence.

---

## Critical Risks

- **R1 — Latency starts in deficit.** The ADR-0029 gate (1.5 s) is already FAIL (~2.1 s)
  without Genesys. Adding a round trip to the Genesys cloud + codec transcoding + one
  more WebSocket hop makes the gate **nearly unreachable** on this path. Risk: freezing
  a decision no measurement supports.
- **R2 — 15-minute cap.** A billing-explanation journey with authentication, BSS lookup,
  PDF extraction and hold time can approach or exceed 15 minutes → Genesys cuts the call
  mid-explanation. No checkpoint/resume is designed.
- **R3 — Degraded modes absent.** If our `wss` endpoint is unavailable or slow, Genesys
  has **no** defined fallback (route straight to advisor queue?). Today = hard failure
  for the caller.
- **R4 — Dual barge-in / end-of-turn logic.** The runtime's bespoke detectors (ADR-0025:
  amplitude threshold, N-frame confirmation) coexist with Genesys-native events
  (`barge-in`, `playback-*`, `BotTurnResponse`). Without an explicit "who owns what per
  path" rule, the runtime fights the protocol → self-interruptions or lost turns.
- **R5 — Handoff mapping unproven.** `EscalationHandoff` (14 fields incl. `summary`,
  `citations`) must travel through **Architect variables / conversation attributes**,
  which have **size/type limits**. A summary + evidence that does not fit = truncated
  handoff.
- **R6 — Concurrency and premium limits.** ≤5 integrations/org + one stream/session + 1
  vCPU VMs: the simultaneous-session ceiling on the Genesys path is **unquantified** (we
  just capped WebRTC at 8 via TASK-WEB-024, with no Genesys-side equivalent).

---

## Hard Questions

1. What is the **measured latency of the Genesys leg** (Architect fork → our `wss` →
   audio back), isolated from other slices? Without it, any V1 trade-off is blind.
2. What does Architect do **when our endpoint is down/times out**? Route straight to the
   advisor queue? Who decides, with what guard delay?
3. Does the billing journey **fit within 15 minutes** in the worst case (auth + slow BSS
   + PDF)? If not: checkpoint/resume or call-back?
4. **PCMU or L16** in the pilot? PCMU forces transcoding (CPU + latency + quality) to the
   PCM16 that Gradium expects.
5. What are the **size limits** on Architect variables / conversation attributes, and
   does the full `EscalationHandoff` fit (otherwise pass an id + backend fetch)?
6. **Data residency / egress**: customer audio (PII) flows from the Genesys cloud to our
   tst VMs — region, encryption, compliance? (overlaps the tst egress open inputs).
7. How many **simultaneous Genesys sessions** at pilot, and does ≤5 integrations + 1 vCPU
   hold that load?

---

## Architecture Challenges

- **Choice: Audio Connector as the target media plane.** *Challenge:* it is the right
  protocol for a bot that speaks, but placing it on the **V1 critical path** before
  passing the latency gate is premature. *Alternative:* keep V1 on the **direct
  web/WebRTC** path (ADR-0033) to prove billing value and the gate, and treat Genesys as
  a **measured feasibility spike** (exactly the ADR-0020 posture) — do not let ADR-0040
  drift into "V1 core" by inertia.
- **Choice: in-house barge-in / end-of-turn detectors on every path.** *Challenge:* on
  the Genesys path they duplicate the native events. *Alternative:* an explicit rule —
  "Genesys path ⇒ **consume** Genesys events, **disable** the in-house energy/amplitude
  detectors"; keep the in-house detectors for the direct WebRTC path only. (Noted as
  intent in ADR-0040; today it is only intent.)
- **Choice: handoff via Architect variables.** *Challenge:* fragile if the payload is
  large. *Alternative:* pass only a **`handoff_id` + `customer_reference`** through
  Architect, and expose a **backend endpoint** the advisor desktop (or a widget) calls to
  fetch the full, audited context — avoids variable limits and keeps the backend the
  owner.
- **Choice: Twilio as fallback (diagram).** *Challenge:* two telephony entries (Genesys +
  Twilio) = two media/latency/barge-in profiles to test. *Alternative:* pick **one**
  pilot entry and explicitly mark the other "not tested in V1".

---

## External Dependency Review

| Dependency | Role (target) | Replaceability | Concern | Recommendation |
|---|---|---|---|---|
| Genesys **Audio Connector** (media) | Bidirectional V2V media plane (AudioHook `wss`) | **Moderate→Hard** (bespoke server, premium, proprietary) | Cloud latency + transcoding + 15-min cap + premium ≤5 | Isolated, measured spike; keep an in-house media port so the runtime is not coupled to the protocol |
| Genesys **Architect + Platform API** (routing) | Transfer/queue/flow-resume on escalation | Moderate | Endpoint-down fallback undefined; variable limits | Define the degraded path + the variable ↔ handoff contract |
| **Gradium** STT/TTS | Reference STT/TTS on the runtime | Moderate (STT/TTS ports exist, cf. TASK-WEB-023) | PCMU→PCM16 transcoding if Genesys is µ-law | Confirm end-to-end L16 or budget the transcoding |
| **Twilio / SIP** | Fallback telephony trunk | Easy (adapter) | Second media profile to test | Decide one pilot entry; mark the other non-V1 |
| **Java backend** (brain) | RAG, billing, guardrails, escalation, memory | Easy (stays in-house) | — | Move nothing to Genesys (per ADR-0001) |

---

## NFR / SLA Gaps

- **No decomposed SLO** for the Genesys legs (Genesys ingress, Architect fork, `wss`
  outbound, transcoding, return, egress). ADR-0020 requires the full round trip — it must
  be instrumented **before** any V1 trade-off.
- **No load test** on the Genesys path (the equivalent of TASK-WEB-024 for WebRTC): the
  session ceiling × 1 vCPU is unknown.
- **No tested degraded mode** (endpoint down, drop, 15-minute timeout, transcode
  failure).
- **Observability**: the correlation id must be **propagated from Genesys**
  (conversationId / participant) into our OpenTelemetry spans — unspecified for this path.
- **Security / PII**: customer audio processed on our VMs; residency/encryption/egress
  undecided.

---

## Recommended Changes

**1. Must fix before industrializing (before Audio Connector becomes V1 core)**

- Measure the **isolated latency of the Genesys leg** and re-score against ADR-0029.
  While the gate is FAIL, Audio Connector stays off the critical path.
- Define and **test degraded modes** (endpoint down → route to advisor queue; drop;
  15-minute timeout).
- Specify the **handoff ↔ Architect contract** (recommended: `handoff_id` + backend
  fetch) with validated size limits.

**2. Should fix before pilot**

- Explicit **barge-in / end-of-turn per path** rule (Genesys events on the Genesys path;
  in-house detectors on direct WebRTC) + tests.
- **Load test** the Genesys path (session ceiling, 1 vCPU, ≤5 integrations) — the
  counterpart of TASK-WEB-024.
- Decide **codec (L16 vs PCMU)** and budget the transcoding; decide **residency/egress**
  for the PII audio.
- **Correlation-id propagation** Genesys → OpenTelemetry end to end.

**3. Can defer**

- Single pilot entry choice Genesys vs Twilio (until the spike decides).
- Optimizations (fine-grained barge-in, Genesys custom SSML/TTS).

---

## Next Step

Recommended operational move: run a **bounded Audio Connector feasibility spike**
(measurement-first: per-leg latency + one degraded mode + a minimal load test) rather
than opening implementation directly, taking the "Must fix" items above as acceptance
criteria. This spike stays gated by OQ-006 and does not move any conversation logic out
of the Java backend.

This spike is now tracked as **TASK-WEB-025** (`product-backlog/tasks/web-voice-tasks.md`),
investigation-only, with the R1–R6 Must-fix items as acceptance criteria.
