# TASK-WEB-025 — Genesys Audio Connector Feasibility Spike: Go/No-Go Report

**Ticket:** TASK-WEB-025 (investigation-only feasibility spike, throwaway prototype)
**Sprint:** 13 — Genesys Audio Connector (`product-backlog/sprints/sprint-13-genesys-audio-connector.md`)
**Decisions of record:** ADR-0049 (delivery shape — **stays Proposed**, this report does not flip it),
ADR-0040 (3-plane split), ADR-0029 (latency gate), DEC-012 (Genesys = full pilot entry; gate not
waived), DEC-013 (handoff by reference), **DEC-014** (spike synthetic-first; concurrency target 3;
pilot env available).
**Date:** 2026-08-28
**Audio posture:** **synthetic / non-PII only** (DEC-014). No real customer audio was used; the
real-PII egress sign-off stays a parallel Security/Compliance item in OQ-006.
**Reproduce:** `cd voice-agent && ./.venv/bin/python spikes/genesys_audiohook/harness.py --turns 50`
**Evidence artifact:** `docs/qa/task-web-025-genesys-synthetic-latency.json`

---

## Executive Summary

- **Overall recommendation: NO-GO for moving the Genesys Audio Connector path onto the ADR-0029
  V1 critical path now — escalate to the user** (per DEC-012: a gate-fail is a user decision on
  mitigation / re-scope / timeline, **not** an auto-proceed and **not** a silent drop of the
  committed direction).
- **The blocker is the in-house mouth-to-ear base, not Genesys transport.** The ADR-0029 re-score
  is a **definitive FAIL at the measured floor**: the last WS-live in-house base (p95 **2760 ms**,
  TASK-WEB-039) already exceeds the **1500 ms** gate before a single Genesys leg is added. The
  measured Genesys transport+transcode overhead is **small** (L16 **~3.3 ms** p95; PCMU **~17.4 ms**
  p95, pure-Python), so the Genesys media plane is **not** the thing that fails the gate — the
  pre-existing in-house latency is (levers: TASK-STT-014 STT tail, TASK-BE-020/BE-033 backend).
- **Codec: prefer L16 end to end.** PCMU forces µ-law companding + resample and costs **~5×** the
  L16 transport overhead in this prototype. L16 needs only an 8 kHz↔16 kHz resample.
- **Concurrency (target = 3, DEC-014): the 1-vCPU concern (R6) is real for a naive transcode.**
  3 concurrent prototype sessions took **~2.96×** a single session's wall time — near-linear
  serialization, because pure-Python transcode is CPU-bound (GIL). A production transcode must use a
  native codec so 3 concurrent Genesys sessions fit the premium ≤5-integrations / 1-vCPU envelope.
- **What this spike could NOT measure (blocked on the live Genesys org):** the Genesys cloud legs
  (ingress, Architect Call-Audio-Connector fork, cloud egress), the codec actually negotiated on the
  pilot org, the 15-minute cap behaviour on a real call, and native barge-in/end-of-turn events.
  These need a human to run a minimal Architect flow (see "Manual Genesys-Architect Steps").
- **ADR-0049 stays Proposed.** It moves toward Accepted only when the live-org measurement lands and
  the residual OQ-006 items sign off.

---

## Scope Tested

- **Epics / stories:** EPIC-007 / EPIC-012, TASK-WEB-025 (the Sprint 13 gate).
- **Prototype:** a **throwaway** in-process AudioHook session (`spikes/genesys_audiohook/`), isolated
  under `spikes/`, **not** wired into the ADR-0047 async server or the production runtime, touching
  **no backend business code** (ADR-0001 boundary invariant holds). It reuses the real ADR-0043
  AudioHook control vocabulary (`web_voice.websocket_framing.ControlType`), the PCM16/16 kHz internal
  boundary, and the real `voice_common` telemetry / pipeline-timing / deterministic `traceparent`.
- **Harness:** `spikes/genesys_audiohook/harness.py` drives N synthetic round trips per codec,
  decomposes per-leg latency, re-scores mouth-to-ear vs ADR-0029, and probes concurrency.
- **Channels / providers:** synthetic wire audio (PCMU + L16) into the prototype; STT/backend/TTS are
  **reused** (not re-measured) via the ADR-0029 WS pilot base.
- **Environment:** co-located dev host (macOS, Python 3.14, pipecat 1.8.1); **warm**; pure-Python
  transcode (the transcode absolute numbers are a dev-host upper bound, not a production budget).

---

## Functional Results (R1–R6 + codec)

| Must-fix | Area | Status | Evidence / decision |
|---|---|---|---|
| **R1** | Isolated Genesys leg + ADR-0029 re-score | ✅ Addressed (synthetic) | Genesys transport overhead measured (L16 ~3.3 ms / PCMU ~17.4 ms p95); full mouth-to-ear re-score = **FAIL floor** (base 2760 ms already > 1500 ms). Cloud legs `measured=false` pending live org. |
| **R2** | 15-minute cap vs billing journey | ⏳ Blocked on live org | Documented as a live-org check; the spike cannot exercise the Genesys call cap synthetically. Mitigation options recorded (checkpoint/resume or call-back) for TASK-WEB-041/044. |
| **R3** | ≥1 degraded mode | ⏳ Blocked on live org (design recorded) | Endpoint-down → fail-safe route to advisor queue is the target (ADR-0049 §5); requires the Architect flow to observe. Prototype ends the session cleanly on close. |
| **R4** | Barge-in / end-of-turn ownership per path | ✅ Decided (confirm on live org) | Genesys native events own the Genesys path; in-house energy/amplitude detectors kept for WS/WebRTC dev only (ADR-0049 §4). Native events to be confirmed on the pilot org. |
| **R5** | Handoff mapping vs Architect limits | ✅ Decided (DEC-013) + size on live org | Transport is **by reference** (`handoff_id` + backend fetch); inline rejected on PII/trust grounds. The minimal routing metadata size vs Architect variable limits is a live-org measurement (TASK-BE-036). |
| **R6** | Concurrency vs premium ≤5 / 1 vCPU | ✅ Addressed (synthetic) | 3 concurrent sessions ≈ 2.96× single-session wall time (GIL-serialized transcode). Target 3 (DEC-014) needs a **native codec** to fit 1 vCPU; premium ≤5-integrations tracked in TASK-INFRA-012. |
| **Codec** | PCMU vs L16 end to end | ✅ Recommendation (confirm on live org) | Prefer **L16** (resample only). PCMU adds ~5× transport overhead (companding). Confirm the pilot org's negotiated codec. |
| **Observability** | Genesys conversationId → one OTel trace | ✅ Addressed | The prototype stamps `correlation_id` on every leg span and the harness derives a W3C `traceparent` from the conversationId (`voice_common.trace_context`), so the Genesys leg + runtime + backend stitch into one trace. |

---

## Latency Results (synthetic, warm; ms)

Per-leg (measured legs only; 50 turns/codec). Cloud legs and STT/backend/TTS are reported
`measured=false` in the JSON artifact per the US-036 rule.

| Leg | Source | PCMU p50 | PCMU p95 | L16 p50 | L16 p95 |
|---|---|---:|---:|---:|---:|
| wss_inbound (framing demux) | synthetic | 0.004 | 0.004 | 0.003 | 0.004 |
| transcode_in (wire→PCM16/16k) | synthetic | 4.16 | 4.25 | 1.89 | 1.93 |
| transcode_out (PCM16/16k→wire) | synthetic | 12.81 | 13.15 | 1.38 | 1.42 |
| wss_outbound (framing) | synthetic | 0.000 | 0.001 | 0.000 | 0.000 |
| **Genesys transport overhead (sum)** | synthetic | **16.96** | **17.38** | **3.27** | **3.33** |
| genesys_ingress / architect_fork / genesys_egress | live org | — | not measured | — | not measured |
| stt / backend / tts | in-house reuse | — | not measured | — | not measured |

ADR-0029 re-score (mouth-to-ear p95 ≤ 1500 ms):

| Codec | In-house base p95 | + Genesys overhead p95 | = Measured floor p95 | Gate | Status |
|---|---:|---:|---:|---:|---|
| PCMU | 2760.0 | 17.38 | **2777.4** | 1500 | **FAIL** |
| L16 | 2760.0 | 3.33 | **2763.3** | 1500 | **FAIL** |

> The floor is a *lower bound*: the unmeasured Genesys cloud legs (ingress/fork/egress) can only
> add. A PASS therefore cannot be reached by trimming the Genesys legs — the in-house base must come
> under budget first. This is the honest R1 result.

Concurrency (target 3, PCMU worst case): single session **38.9 ms** → 3 concurrent **115.0 ms**
(**2.96×**). Near-linear serialization on 1 vCPU for a pure-Python transcode.

---

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| AudioHook transport framing | ✅ Reusable | The ADR-0043 JSON-control + binary-PCM16 framing shape maps 1:1; framing cost is negligible (~µs). | Genuine transport-adapter swap in TASK-WEB-041. |
| Codec transcode | ⚠️ Budget item | PCMU companding dominates the (dev-host) overhead; L16 far cheaper. Pure-Python is CPU-bound. | Prefer L16; if PCMU, use a native codec (TASK-WEB-041). |
| Concurrency on 1 vCPU | ⚠️ Risk (R6) | Naive transcode serializes; 3 sessions ≈ 3× CPU. | Native codec + measure again on a 1-vCPU-class runtime (TASK-WEB-043). |
| Observability | ✅ Ready | conversationId → deterministic traceparent → one trace; per-leg spans emitted. | Reuse for TASK-WEB-043 per-leg slices on the live path. |
| ADR-0029 gate | ❌ Fail (floor) | In-house base already over budget; Genesys adds little but cannot rescue it. | Escalate to user; pursue in-house latency levers first. |

---

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| High | ADR-0029 mouth-to-ear gate FAILs at the measured floor (in-house base 2.76 s) | Genesys path cannot go on the V1 critical path now | User decision (DEC-012) + TASK-STT-014 / TASK-BE-020/BE-033 |
| Medium | Genesys cloud legs unmeasured | R1 re-score is a floor, not the true total | Live Genesys org (TASK-INFRA-012) |
| Medium | PCMU transcode + 1-vCPU concurrency cost | R6 envelope risk at target 3 | Native codec in TASK-WEB-041 / measure in TASK-WEB-043 |
| Low | 15-min cap + degraded modes not exercised | R2/R3 unproven on a real call | Live org (TASK-WEB-041/044 + TASK-INFRA-012) |

---

## Open Questions (residual OQ-006)

- **Product / Architecture:** given the FAIL floor is driven by the in-house base, does Sprint 13
  proceed with the Genesys build slices (TASK-WEB-041..044) in parallel with the in-house latency
  levers, or hold the Genesys build until the base is under budget? **(user decision — DEC-012)**
- **Security / Compliance:** PII-audio residency / egress sign-off — **still OPEN, parallel track**,
  not a spike blocker (DEC-014). Aligned with OQ-009.
- **Architecture (live org):** codec negotiated on the pilot org; Architect variable/attribute size
  limits for the `handoff_id` + minimal routing metadata; native barge-in/EOT event confirmation.

---

## Recommendation

- **Go / No-Go: NO-GO** to placing the Genesys Audio Connector path on the ADR-0029 V1 critical path
  at this time. **This NO-GO escalates to the user** (DEC-012) — it is not an auto-proceed and not a
  silent drop of the committed Genesys direction; the follow-on tickets (TASK-WEB-041..044,
  TASK-BE-036/037, TASK-INFRA-012) carry forward pending the user's call.
- **Why:** the gate fails on the **in-house** mouth-to-ear base (2.76 s > 1.5 s), not on the Genesys
  transport (L16 ~3 ms / PCMU ~17 ms overhead). The Genesys media plane is feasible as a transport
  adapter and cheap on L16; it simply cannot rescue an already-over-budget base.
- **Required before a GO re-score can even be attempted:**
  1. Bring the in-house mouth-to-ear p95 under (or near) 1.5 s (TASK-STT-014 STT tail; TASK-BE-020 /
     TASK-BE-033 backend first-token).
  2. Run the **live Genesys org** measurement (manual Architect steps below) to fill the cloud legs
     and confirm codec / cap / native events.
  3. Confirm a **native transcode** so 3 concurrent sessions fit 1 vCPU (R6).
- **ADR-0049:** remains **Proposed**. Do **not** flip to Accepted until the live-org measurement lands
  and the residual OQ-006 items sign off. (Update hooks scaffolded in the ADR's Status section.)

---

## What Still Needs the Live Genesys Org

The synthetic spike proves the transport/transcode/observability shape and the FAIL floor. The
following require the pilot org (available now per DEC-014) and a human in Architect:

### Manual Genesys-Architect Steps (human-run)

1. **Expose the throwaway `wss` endpoint** reachably (dev tunnel or the pilot edge) so the pilot org
   can reach it; note the URL + the auth the Audio Connector requires.
2. **Create a minimal Architect inbound call flow** with a **Call Audio Connector** action:
   - configure the Audio Connector integration pointing at the `wss` endpoint (record which of the
     premium ≤5 integrations slot it consumes — R6);
   - **fork + pause** the flow to stream call audio to the endpoint.
3. **Place a test call** (synthetic/non-PII speech) and capture, under the Genesys `conversationId`:
   - Genesys **ingress → fork** time and **egress** time (the cloud legs — R1);
   - the **codec** actually negotiated (PCMU vs L16 — confirm the L16 recommendation);
   - native **barge-in / playback-started / playback-completed / BotTurnResponse** events (R4).
4. **Hold the call past ~15 minutes** (or inspect org policy) to confirm the **call cap** and whether
   the worst-case billing journey fits or needs checkpoint/resume / call-back (R2).
5. **Make the endpoint unavailable / time out mid-call** and observe the Architect behaviour; confirm
   it **fails safe to the billing advisor queue** and the flow resumes cleanly at session end (R3).
6. **On session end, route to the billing advisor queue** carrying only the `handoff_id` + minimal
   routing metadata; record the Architect **variable/attribute size + type limits** (R5, TASK-BE-036).
7. **Re-run** `spikes/genesys_audiohook/harness.py` with the measured cloud-leg values fed in as the
   base, so the ADR-0029 re-score includes the true Genesys legs.

Only after these land does ADR-0049 move Proposed → Accepted (on a GO) — or stay parked at Proposed
with the NO-GO rationale (this report), per the sprint exit criteria.
