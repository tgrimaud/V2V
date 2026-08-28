# Sprint 13 — Genesys Audio Connector + Genesys Integration

## Sprint Objective

Bring the target **Genesys** integration from an accepted-on-paper decision
(ADR-0040) to a **measured, de-risked, and specified** state, so a Genesys-fronted
Voice2Voice call can reach the in-house voice runtime over the **Audio Connector**
feature of AudioHook, get a grounded answer from the Java backend, and hand off to a
human advisor with usable context — **without moving any conversation intelligence
into Genesys**.

**Strategic direction is decided (2026-08-27):** per **DEC-012**, Genesys **is** the
full phone entry point for the pilot and full Audio Connector voice routing **is** the
pilot target (not a spike-only experiment); per **DEC-013**, the escalation handoff
travels **by reference** (`handoff_id` + backend fetch). What Sprint 13 gates is the
**technical feasibility**, not the direction.

The sprint is therefore **gate-first on latency/feasibility**. It opens with the
investigation-only spike (**TASK-WEB-025**, gated by **OQ-006** pilot access) whose
go/no-go on the **measured Genesys leg vs the ADR-0029 budget** unblocks the follow-on
implementation tickets. Every follow-on ticket is **Proposed and conditional** on that
feasibility result plus OQ-006 pilot access. Committing to Genesys as the entry does
**not** waive the gate: if the spike measures the Genesys leg as **gate-failing**, that
is an **escalation to the user** for a decision (mitigation / re-scope / timeline) —
**not** an auto-proceed onto the V1 critical path and **not** a silent drop of the
committed direction. On such a NO-GO the sprint closes on the spike report + updated
ADRs and the follow-on tickets carry forward pending the user's call.

**Design invariant (enforced at review, all Sprint 13 tickets):** the Java backend
remains the source of truth for the AI conversation workflow, RAG, billing reasoning,
guardrails, escalation policy, handoff content, and conversation memory (ADR-0001).
Genesys Cloud CX stays the contact-center system of record — call ingestion, IVR/ANI,
recording, routing, queues, supervision, reporting, advisor desktop. The Audio
Connector media plane is delivered as **one more transport adapter** on the ADR-0047
single async HTTP+WebSocket server, reusing the ADR-0043 transport-agnostic session
factory and the PCM16/16 kHz internal boundary — **not** a parallel stack.

**Decisions of record:** **DEC-012** (Genesys = full phone entry point for the pilot;
full Audio Connector voice routing is the pilot target, US-018 deferred — the
TASK-WEB-025 latency/feasibility gate still applies), **DEC-013** (escalation handoff
travels **by reference** — `handoff_id` + backend fetch; inline context rejected on
PII/trust-boundary grounds), **DEC-014** (spike synthetic-first; concurrency target 3;
pilot env available), **DEC-015** (**DECOUPLE** — the ADR-0029 latency gate is decoupled
from the Genesys connector build; the build proceeds while the gate is tracked as a
separate latency workstream; no Genesys-path SLO claim until the base latency closes),
ADR-0040 (Genesys Audio Connector 3-plane split — updated
this sprint), **ADR-0049** (Genesys Audio Connector Sprint 13 delivery shape — new,
Proposed/spike-gated on technical feasibility). Builds on ADR-0046 (WebSocket primary
transport) + ADR-0047 (single async server) + ADR-0043 (session factory) +
ADR-0019/0020 (escalation + handoff) + ADR-0009 (channel envelope) + ADR-0029 (latency
gate) + ADR-0025 (barge-in).

## Status

**Status:** 🚧 **In progress** (kicked off 2026-08-28) — **strategic direction decided**
(DEC-012 Genesys = full pilot entry; DEC-013 handoff by reference; **DEC-014** spike
synthetic-first + concurrency target 3 + pilot env available). Implementation gated by
**OQ-006** (residual technical/compliance items).

**Spike outcome + gate posture (2026-08-28, DEC-015 — DECOUPLE).** The **TASK-WEB-025**
feasibility spike is **delivered** (go/no-go report + synthetic latency artifact). It
returned a **NO-GO against ADR-0029** — a **FAIL at the measured floor** — but the failure
is **base-latency-driven, not Genesys-driven**: the Genesys transport/transcode is cheap
(**L16 ~3.3 ms / PCMU ~17.4 ms** p95 overhead), while the pre-existing in-house
mouth-to-ear base (p95 **~2.76 s**, TASK-WEB-039) already exceeds the 1.5 s budget before
any Genesys leg. The user **resolved the DEC-012 escalation as DECOUPLE (DEC-015)**: the
**Genesys connector build proceeds** (spike is **GO-for-build**), and the **ADR-0029 gate
is tracked as a separate latency workstream** (documented **FAIL**, owned by TASK-BE-033
model choice / OpenAI key + TASK-STT-014 + TASK-BE-020). **No SLO is claimed on the Genesys
path** until the base latency comes under budget and ADR-0029 is re-scored PASS. The
follow-on build tickets are therefore **unblocked from the gate** but remain conditional on
**OQ-006 pilot access + the live-org cloud-leg measurement** (runbook:
`docs/operations/genesys-live-measurement-runbook.md`), which completes what the synthetic
spike could not (Genesys cloud legs, negotiated codec, 15-min cap, native barge-in/EOT).

**Sprint branch:** `feat/sprint-13-genesys-audio-connector` (forked from
`feat/restart-from-scratch`, 2026-08-27; **synced with mainline 2026-08-28 via
`--no-ff` merge `8b9bc5a`** so the rebuilt `backend/` + `voice-agent/` are present).
Two-level branch model: ticket branches fork from and merge back into this sprint branch
(`git merge --no-ff`); the sprint branch merges into `feat/restart-from-scratch` only on
the user's explicit request at sprint closure.

## Roadmap Context

> **Scope note (2026-08-27):** the Sprint 13 registry row historically read
> *"Telephony channel (US-018) + Genesys Audio Connector + advisor handoff"*. This
> sprint **narrows the theme to Genesys** (Audio Connector media plane + advisor
> handoff, EPIC-007/012). **Telephony as a separate Twilio/SIP entry (US-018) is moved
> OUT** — Genesys is the target contact-center entry, so a second telephony media
> profile is deferred until the Genesys spike decides the single pilot entry (the
> adversarial review's "one pilot entry" recommendation). US-018 stays in the backlog,
> not dropped.

| Sprint | Theme | State |
|---|---|---|
| Sprint 11 | Remote deployment & release readiness (eir-ai4cc-tst) | ✅ Done (2026-08-24) |
| Sprint 12 | External voice via interim WebSocket audio (Genesys-ready) | ✅ Done (2026-08-25, v0.6.0) |
| **Sprint 13** | **Genesys Audio Connector + Genesys integration** | 🚧 In progress — TASK-WEB-025 spike (synthetic-first) |
| Sprint 14 (tentative) | Customer identity + BSS/PDF evidence + deterministic comparison (EPIC-002/003/004) | Planned — gated by OQ-001/003/004 |

## Why now (state that justifies the sprint)

- **The capital is in place.** Sprints 12 + the ADR-0046/0047 transport consolidation
  built exactly what Genesys needs: an AudioHook-shaped `wss` transport (JSON control
  frames + binary PCM16/16 kHz audio), a **transport-agnostic session factory**
  (ADR-0043), a PCM16/16 kHz internal boundary with codec conversion inside adapters,
  a **pluggable control-signal seam**, and — since ADR-0047 / TASK-WEB-038 — a **single
  async HTTP+WebSocket server** that is the natural host for the Audio Connector
  `wss://` endpoint. Genesys is now a **transport-adapter swap**, not a greenfield build.
- **The decision was reviewed and conditionally approved.** The 2026-08-07 adversarial
  review scored the target 2.2/5 and said *"proceed with conditions — as a bounded,
  measured feasibility spike, NOT as V1 core"*, raising six Must-fix risks (R1–R6). This
  sprint is the vehicle that answers them by measurement before any commitment.
- **V1 needs a credible human escalation path** on the target contact-center
  (ADR-0019/0020). The handoff transport contract (Architect variables vs
  `handoff_id` + backend fetch) is unproven and must be settled.
- **The latency gate is honest but currently FAIL** (ADR-0029 mouth-to-ear p95 ≤ 1.5 s;
  last WS-live pilot sample 2.76 s, TASK-WEB-039). Adding a Genesys cloud round trip can
  only add latency, so the Genesys leg must be **isolated and measured** before it goes
  anywhere near the V1 critical path.

## Scope IN

0. **Full Genesys voice-entry routing is the pilot target (DEC-012).** Genesys is the
   full phone entry point for pilot calls — inbound calls ingress via Genesys and route
   to the in-house runtime over the Audio Connector, plus advisor handoff. This is the
   committed direction; it is delivered **gated by the TASK-WEB-025 latency/feasibility
   GO** (a gate-fail escalates to the user, per the Status note above). US-018
   (Twilio/SIP as a separate entry) stays OUT.
1. **Latency/feasibility spike / go-no-go (the gate):** measure the isolated Genesys-leg
   latency and re-score against ADR-0029; confirm codec (L16/PCMU) and the 15-minute
   cap against the billing journey; characterise ≥1 degraded mode; size the by-reference
   handoff's minimal routing metadata vs Architect limits (transport already decided —
   DEC-013); define barge-in/end-of-turn ownership per path; and a minimal concurrency
   ceiling. Throwaway prototype + report (TASK-WEB-025).
2. **Audio Connector transport adapter** (conditional on GO): an AudioHook `wss://`
   endpoint on the ADR-0047 unified server, via the ADR-0043 session factory —
   PCMU/L16 ↔ PCM16 codec conversion inside the adapter, one bidirectional
   stream/session, 15-minute-cap handling (TASK-WEB-041).
3. **Barge-in / end-of-turn ownership per path** — consume Genesys native events on
   the Genesys path; keep the in-house energy/amplitude detectors for the WS/WebRTC dev
   path only (TASK-WEB-042).
4. **Genesys-path concurrency ceiling + per-channel observability** — minimal
   concurrent-session ceiling + backpressure, per-channel gauges, per-leg latency
   slices, and correlation-id propagation from Genesys into OpenTelemetry (TASK-WEB-043).
5. **Degraded-mode behaviors** — endpoint down/slow/timeout, session drop,
   15-minute timeout mid-call, transcode failure → fail-safe route to the advisor queue
   (TASK-WEB-044).
6. **EscalationHandoff transport contract** — the **decided** by-reference shape
   (DEC-013): `handoff_id` + backend fetch, ADR-0019 payload + PII stay backend-owned;
   inline Architect-variable context is rejected on PII/trust-boundary grounds. The
   spike sizes the minimal routing metadata vs Architect limits (TASK-BE-036).
7. **Normalized channel envelope for the Genesys adapter** — `channel`,
   `external_session_id`, `message_id`, `idempotency_key`, `reply_mode`,
   `escalation_context` (ADR-0009), so escalation/routing/memory stay backend-owned and
   consistent across channels (TASK-BE-037).
8. **Genesys Architect flow + control/routing plane config** — the Call Audio
   Connector action forks + pauses the flow to our `wss` endpoint; on session end the
   flow resumes and routes to the billing advisor queue; queue/skill routing; endpoint
   exposure/TLS/auth (TASK-INFRA-012).

## Scope OUT

- **Moving any conversation logic into Genesys** — RAG, billing reasoning, guardrails,
  escalation policy, handoff content, and memory stay in the Java backend (ADR-0001).
  Genesys-native voicebots (Dialogflow/Lex/Nuance) are explicitly rejected (ADR-0040).
- **Telephony as a separate Twilio/SIP entry (US-018)** — deferred (see the scope note
  above); one pilot entry is chosen by the spike.
- **Full production hardening / SLO claim on the Genesys path** — the spike is
  investigation-only; a production SLO still requires the ADR-0010 operational controls
  on top of a measured baseline.
- **Billing/identity, BSS/PDF evidence, deterministic comparison** — Sprint 14.
- **Any change to what the bot says** — DEC-002 grounding stays enforced; this sprint
  changes *how a Genesys-fronted call reaches the runtime and hands off*, not answer
  content.
- **Compliance/data-residency sign-off for PII audio** egress from the Genesys cloud to
  the runtime VMs — surfaced by the spike as an OQ-006 decision item; not resolved here.

## Tickets (ordered)

| # | Ticket | Title | Role | Gate | Status |
|---|---|---|---|---|---|
| 1 | TASK-WEB-025 | Genesys Audio Connector **feasibility spike** (investigation only) — go/no-go | Investigate (the gate) | OQ-006 | 🚧 In progress (synthetic-first, DEC-014) |
| 2 | TASK-WEB-041 | Genesys **Audio Connector transport adapter** on the ADR-0047 server — codec (PCMU/L16 ↔ PCM16) + one stream/session + 15-min cap | Build (runtime) | spike GO | 📋 Proposed |
| 3 | TASK-WEB-042 | **Barge-in / end-of-turn ownership per path** — Genesys native events on the Genesys path; in-house detectors on WS/WebRTC dev only | Build (runtime) | spike GO | 📋 Proposed |
| 4 | TASK-WEB-043 | Genesys-path **concurrency ceiling + per-channel observability** — per-leg latency slices + correlation-id propagation | Build (runtime + observability) | spike GO | 📋 Proposed |
| 5 | TASK-WEB-044 | Genesys-path **degraded modes** — fail-safe route to the advisor queue on endpoint down/timeout/drop/cap | Build (runtime + infra) | spike GO | 📋 Proposed |
| 6 | TASK-BE-036 | **EscalationHandoff transport contract** — `handoff_id` + backend fetch (ADR-0019 payload backend-owned), vs Architect-variable size limits | Build (backend) | spike GO | 📋 Proposed |
| 7 | TASK-BE-037 | **Normalized channel envelope** for the Genesys adapter (`channel`, `external_session_id`, `message_id`, `idempotency_key`, `reply_mode`, `escalation_context`) | Build (backend) | spike GO | 📋 Proposed |
| 8 | TASK-INFRA-012 | **Genesys Architect flow + control/routing plane** config — Call Audio Connector fork/resume + advisor-queue routing + `wss` endpoint exposure | Wire (infra/config) | spike GO + OQ-006 | 📋 Proposed |

Full ticket details: TASK-WEB-025/041/042/043/044 in `tasks/web-voice-tasks.md`;
TASK-BE-036/037 in `tasks/backend-hardening-tasks.md`; TASK-INFRA-012 in
`tasks/deployment-tasks.md`.

## Dependencies & Sequencing

```
OQ-006 (pilot access + handoff shape)  ─┐
                                        ├─▶  TASK-WEB-025 (spike / go-no-go)  ──▶ GO?
ADR-0047 single async server (done) ────┘                                         │
                                                                                  ▼
        ┌──────────────────────────────────────────────────────────────────────────┐
        │  On GO (all conditional):                                                  │
        │  TASK-WEB-041 (transport adapter) ──┬─▶ TASK-WEB-042 (barge-in ownership)   │
        │                                     ├─▶ TASK-WEB-043 (concurrency + obs.)   │
        │                                     └─▶ TASK-WEB-044 (degraded modes)       │
        │  TASK-BE-037 (channel envelope) ────────▶ TASK-BE-036 (handoff transport)   │
        │  TASK-INFRA-012 (Architect flow) ── pairs with TASK-WEB-041 + TASK-WEB-044  │
        └──────────────────────────────────────────────────────────────────────────┘
```

- **TASK-WEB-025 is the gate.** Nothing downstream commits before its go/no-go.
- **TASK-WEB-041** (transport adapter) is the spine; 042/043/044 refine the live
  behaviour on it. **TASK-INFRA-012** (Architect flow) is co-developed — the media
  adapter is untestable end-to-end without the fork/resume flow.
- **TASK-BE-037** (channel envelope) precedes **TASK-BE-036** (handoff transport): the
  handoff payload rides the envelope fields.
- The spike may re-order or fold follow-ons based on what it finds (e.g. if PCMU
  transcoding is heavier than budget, 041 grows; if the 15-minute cap forces
  checkpoint/resume, that becomes an explicit 041 sub-item or a new ticket).

## Must-fix traceability (adversarial review 2026-08-07, R1–R6)

Every Must-fix risk maps to a ticket and an acceptance hook.
Source: `docs/architecture/reviews/genesys-audio-connector-adversarial-review-2026-08-07.md`.

| Must-fix | Risk (short) | Ticket(s) | Acceptance hook |
|---|---|---|---|
| **R1** | Latency starts in deficit; Genesys leg unmeasured (ADR-0029 already FAIL) | TASK-WEB-025 (measure isolated leg + re-score), TASK-WEB-043 (per-leg slices + correlation id) | Isolated Genesys-leg p50/p95 reported; full round trip re-scored vs ADR-0029 with a go/no-go note; per-leg slices emitted on the live path |
| **R2** | 15-minute cap may cut a billing journey mid-explanation | TASK-WEB-025 (confirm cap vs journey), TASK-WEB-041 (cap handling), TASK-WEB-044 (cap-timeout degraded mode) | Cap confirmed against the worst-case journey; checkpoint/resume-or-callback decision recorded; adapter behaviour on cap defined + a fail-safe on cap timeout |
| **R3** | Degraded modes absent (endpoint down/slow/timeout/drop) | TASK-WEB-044 (fail-safe → advisor queue), TASK-INFRA-012 (Architect fallback) | ≥1 degraded mode characterised in the spike + a tested fail-safe route to the advisor queue; Architect behaviour on endpoint-down documented |
| **R4** | Dual barge-in / end-of-turn logic fights the protocol | TASK-WEB-042 (per-path ownership) | On the Genesys path barge-in/end-of-turn/playback are owned by **Genesys events**; the in-house energy/amplitude detectors are **disabled** there and kept only for WS/WebRTC dev |
| **R5** | Handoff mapping unproven vs Architect-variable size limits | TASK-BE-036 (handoff transport), TASK-BE-037 (channel envelope) | Architect variable/attribute size+type limits documented; transport **decided by reference** (DEC-013: `handoff_id` + backend fetch, inline rejected on PII grounds); `EscalationHandoff` + PII stay backend-owned |
| **R6** | Concurrency + premium limits unquantified (≤5 integrations, 1 stream/session, 1 vCPU) | TASK-WEB-043 (concurrency ceiling), TASK-INFRA-012 (integration count / Architect) | Minimal concurrent-session ceiling measured on a 1-vCPU-class runtime; premium ≤5-integrations impact recorded; per-channel backpressure honoured |

## Observability & latency expectations (ADR-0029 + ADR-0028)

- **Per-leg decomposition (mandatory before any Genesys latency trade-off).** The
  Genesys round trip adds legs the WS/WebRTC paths do not have: Genesys ingress →
  Architect Call-Audio-Connector fork → our `wss` inbound → **transcoding** (if PCMU) →
  STT → backend → TTS → `wss` outbound → transcoding → Genesys egress. Each leg is a
  slice reported p50/p95; un-instrumented legs are emitted `measured=false` with a
  reason (US-036 rule), never omitted (TASK-WEB-043).
- **The ADR-0029 gate (mouth-to-ear p95 ≤ 1.5 s / TTFA p95 ≤ 1.2 s) is re-scored with
  the Genesys leg included** — while the gate is FAIL, the Audio Connector path stays a
  measured spike and does **not** move onto the V1 critical path (adversarial review
  R1). No pilot SLO is claimed on the Genesys path in this sprint.
- **Correlation-id propagation** — the Genesys `conversationId` / participant id is
  carried into the OpenTelemetry spans across the full round trip, so the Genesys leg,
  the runtime, and the backend land in **one trace** (TASK-WEB-043; mirrors the
  voice→backend deterministic `traceparent` approach).
- **Codec transcoding is an explicit budget item** — PCMU (µ-law) forces a transcode to
  the Gradium PCM16 expectation (CPU + latency + quality); L16 maps directly. The spike
  records which codec the pilot uses and budgets the transcode (TASK-WEB-025/041).

## Risks & Degraded Modes

| Risk / failure mode | Design response (this sprint) |
|---|---|
| Our `wss` endpoint down / slow / times out | Architect fail-safe → route straight to the advisor queue; flow resumes cleanly at session end (TASK-WEB-044 + TASK-INFRA-012) |
| Session dropped mid-call | Bounded reconnect window then fail-safe to advisor; conversation memory preserved backend-side (TASK-WEB-044, ADR-0044 degradation posture) |
| 15-minute cap hit mid-explanation | Cap-timeout fail-safe + the checkpoint/resume-or-callback decision from the spike (R2 → TASK-WEB-041/044) |
| Transcoding failure (PCMU) | Fail closed to a safe hand-off; codec confirmed L16 end-to-end where possible to avoid it (TASK-WEB-041) |
| Genesys premium ≤5 integrations / 1 stream/session / 1 vCPU | Minimal concurrency ceiling + backpressure measured; integration budget tracked (R6 → TASK-WEB-043 + TASK-INFRA-012) |
| Handoff payload exceeds Architect-variable limits | `handoff_id` + backend fetch keeps the full audited payload backend-side (R5 → TASK-BE-036) |
| Latency regression pushes the gate further FAIL | Genesys path stays a spike off the critical path until the gate is re-scored PASS (R1 → TASK-WEB-025/043) |
| Barge-in self-interruption / lost turns from dual logic | Genesys events own barge-in/EOT on the Genesys path; in-house detectors disabled there (R4 → TASK-WEB-042) |

## Exit Criteria / Definition of Done

**Gate outcome (always required):**

- **TASK-WEB-025 delivers a go/no-go report** answering R1–R6 by measurement: isolated
  Genesys-leg p50/p95 + ADR-0029 re-score; codec (L16/PCMU) confirmed end-to-end;
  15-minute cap checked against the worst-case billing journey; ≥1 degraded mode
  characterised; barge-in/end-of-turn ownership decided; minimal concurrency ceiling
  measured; the by-reference handoff's minimal routing metadata sized vs Architect
  limits (transport already decided — DEC-013).
- **ADR-0040 is updated and ADR-0049 moves from Proposed toward Accepted** (or is
  explicitly parked at Proposed with the NO-GO rationale), and **OQ-006** items the
  spike resolved are recorded.

**On spike GO (conditional follow-on DoD):**

- A **Genesys-fronted call** reaches the runtime over the Audio Connector `wss`
  endpoint, gets a grounded backend answer, and returns bot audio — via the Audio
  Connector transport adapter on the ADR-0047 server (TASK-WEB-041 + TASK-INFRA-012).
- **Barge-in and end-of-turn on the Genesys path are driven by Genesys events**, with
  the in-house detectors disabled on that path and unchanged on WS/WebRTC
  (TASK-WEB-042).
- The Genesys path **emits per-leg latency slices under one correlation id** and honours
  a measured concurrency ceiling with backpressure (TASK-WEB-043).
- At least one **degraded mode is implemented and tested** (endpoint down → advisor
  queue) with a fail-safe that never leaves the caller stranded (TASK-WEB-044).
- **Escalation hands off with usable context** through the decided transport
  (`handoff_id` + backend fetch), the `EscalationHandoff` payload stays backend-owned,
  and the normalized channel envelope is populated by the Genesys adapter
  (TASK-BE-036 + TASK-BE-037).
- The **Genesys boundary holds**: no RAG, billing reasoning, guardrail, escalation
  policy, handoff content, or memory moved into Genesys (confirmed at adversarial
  review, ADR-0001/0040).

**Process gates (per ticket, unchanged):**

- Each ticket passes adversarial review ≥ 90% (or explicit residual-risk acceptance),
  then QA (functional + latency where runtime-affecting), with OpenTelemetry coverage.
- Passing all gates makes the branch **merge-ready only**. Merge (ticket→sprint and
  sprint→`feat/restart-from-scratch`) happens **only on the user's explicit request**.

## Decisions & Open Items (OQ-006)

**✅ Decided by the user (2026-08-27):**

1. **Full Genesys Audio Connector voice routing IS required for the pilot** — the pilot
   target, not spike-only (**DEC-012**). The TASK-WEB-025 latency/feasibility gate still
   applies; a gate-fail escalates to the user.
2. **Genesys IS the phone entry point for pilot calls** (**DEC-012**) — the media plane
   ships for the pilot (gated by the spike GO).
3. **Handoff transport = by reference** (**DEC-013**): `handoff_id` + backend fetch;
   inline Architect-variable context **rejected** (PII/trust boundary). Only the
   `handoff_id` + minimal routing metadata cross the Genesys boundary.
4. **Single pilot entry = Genesys** (**DEC-012**) — Twilio/SIP (US-018) deferred, marked
   not-tested-in-V1.

**✅ Decided by the user (2026-08-28, DEC-014):**

5. **Spike PII posture = synthetic-first** — TASK-WEB-025 runs on **synthetic / non-PII
   audio only**. The real-PII egress sign-off is a **parallel** Security/Compliance item,
   **NOT a spike blocker**, and stays OPEN in OQ-006.
6. **Pilot concurrency target = 3** concurrent Genesys sessions — the spike checks this
   fits the premium **≤5-integrations / 1-vCPU** envelope (R6).
7. **Genesys pilot environment is available now** (org + Architect access) — the
   live-measurement steps are human-runnable once the throwaway prototype is ready.

**✅ Decided by the user (2026-08-28, DEC-015 — resolves the TASK-WEB-025 escalation):**

8. **DECOUPLE the ADR-0029 gate from the Genesys build.** The spike NO-GO (escalated under
   DEC-012) is resolved: the **Genesys connector build proceeds** (TASK-WEB-041 + follow-ons
   are unblocked from the gate) and the **ADR-0029 gate is a separate latency workstream**
   (documented **FAIL**, owned by TASK-BE-033 model choice / OpenAI key + TASK-STT-014 +
   TASK-BE-020). **No Genesys-path SLO** is claimed until the base latency closes and ADR-0029
   is re-scored PASS. ADR-0049 **stays Proposed** — build authorized under the decouple; the
   flip to Accepted still needs the live-org re-score (GO) + OQ-006 sign-off. The build tickets
   remain conditional on **OQ-006 pilot access + the live-org measurement** (see the runbook
   `docs/operations/genesys-live-measurement-runbook.md`), not on an ADR-0029 PASS.

**⏳ Still open — surfaced for the decision owner; the spike (or the named owner) must
resolve before the Genesys path is accepted:**

1. **Codec:** PCMU or L16 end to end? PCMU forces transcoding — a latency/CPU/quality
   cost. *(spike — TASK-WEB-025)*
2. **15-minute cap:** does the worst-case billing journey (auth + slow BSS + PDF + hold)
   fit, or is checkpoint/resume / call-back needed? *(spike — TASK-WEB-025)*
3. **Which customer/session identifiers** the pilot trust model allows as the minimal
   routing metadata alongside the `handoff_id`. *(spike — TASK-WEB-025)*
4. **Data residency / egress for PII audio** from the Genesys cloud to the runtime VMs —
   region, encryption, compliance sign-off. **(user — Security / Compliance)** — **still
   OPEN, parallel track, not a spike blocker (DEC-014)**; the spike runs synthetic-only.
5. **Concurrency at pilot:** the **target is 3 concurrent Genesys sessions (DEC-014)**; the
   spike verifies it holds within the premium ≤5-integrations + 1-vCPU envelope. *(spike —
   TASK-WEB-025 + product)*
