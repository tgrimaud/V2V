# Remaining Work Recap — objective of each open/in-flight ticket

> **Snapshot: 2026-09-28 (refreshed after the WIP close-out).** Plain-language purpose
> ("the why") of each ticket that is still open, in-flight, or on an unmerged branch, so the
> goal is understood at a glance. This is a point-in-time summary — the authoritative status
> always lives in the ticket file and `backlog-index.md`. Regenerate/refresh when the picture
> changes materially.
>
> **Closed since the first snapshot (all merged into `feat/restart-from-scratch`):**
> BUG-024 symptom (b) (`6adb781`, review 92/100), TASK-BE-033 lever-2 prefill-trim (`0232e34`,
> review 95/100, shipped default-off). TASK-BE-024 / TASK-BE-025 were already merged + shipped
> since v0.5.0 (recap was stale — no action needed). Mainline backend `mvn clean test` = **642/0/0**.

## Bugs to finish

| Ticket | Objective (the why) | State |
|---|---|---|
| ~~BUG-005~~ | Stop internal KB passages (notes, non-customer content) from surfacing in an answer. | ✅ Merged (`002eff9`), shipped since v0.4.0 |
| ~~BUG-006~~ | Ensure the VIP actually fails over to the standby when the active node dies (VRRP failover weight). | ✅ Merged (`7b1ba56`), shipped since v0.5.0 (live 2-node retest = deferred nice-to-have) |
| ~~BUG-008~~ | Don't count an interrupted/failed TTS synthesis in the "time to first audio" latency (it skews p95). | ✅ Merged (`2fe8260`), shipped since v0.5.0 |
| ~~BUG-016~~ | Stop refusing legitimate EN turns because an off-topic pattern matched inside a word (`king` ⊂ `working`). | ✅ Merged (`35d95d1`), shipped since v0.6.0 |
| **BUG-017** | Explain/fix the inconsistent barge-in (interruption) counter on the headless WebSocket path. | New — investigate |
| **BUG-018** | Never leave the UI stuck on "Thinking" when a turn fails server-side. | 2/3 done; remaining = TASK-OPS-010 drain + server-side `turn_error` terminal signal |
| ~~BUG-019~~ | Don't claim a billing discrepancy was "explained" when the cause was not actually determined. | ✅ Merged (`158a626`, Sprint-14 `5650e15`), shipped since v0.9.0 |
| ~~BUG-020~~ | Return a controlled error/message when an invoice can't be fetched, instead of a 500 crash. | ✅ Merged (`fecf3ef`, review 95/100), shipped since v0.9.0 |
| **BUG-024** | Keep the useful grounded answer even when a courtesy/hand-off sentence trails it (don't drop it). | ✅ Symptom (b) merged (`6adb781`). ⏳ Symptom (a) dead-air (audible hand-off on LLM stream error) still deferred — needs a voice-tier repro. |

## Tasks in flight (WIP)

| Ticket | Objective (the why) | State |
|---|---|---|
| **TASK-BE-058** | In auto mode (no UI selection), keep the conversation language stable — only switch when the current turn detects the other language with a real margin (not a lone accent). Prevents fr/en oscillation. (Secondary of BUG-026.) | Not implemented (follow-up ticket) |
| ~~TASK-BE-033 (prefill-trim)~~ | Trim the context sent to the LLM (token budget) to speed up first-sentence generation (latency lever 2). | ✅ Merged (`0232e34`, default-off) |
| ~~TASK-BE-024~~ | Harden conversation-memory persistence/read (consistency, limits, error cases). | ✅ Already merged + shipped since v0.5.0 |
| ~~TASK-BE-025~~ | Put controlled timeouts on outbound calls (LLM, embedding, BSS) so a turn never blocks indefinitely. | ✅ Already merged + shipped since v0.5.0 |

## Genesys (real-time telephony)

| Ticket | Objective (the why) | State |
|---|---|---|
| **TASK-WEB-044** | Define safe behavior when Genesys is slow/absent/dropped (timeout, drop, 15-min cap, transcode failure) → fail-safe route to the advisor queue (Architect) with auditable reasons. Required before any prod Genesys SLO. | Open |

## Latency (ADR-0029 gate still FAIL)

| Ticket | Objective (the why) | State |
|---|---|---|
| **TASK-STT-014** | Shorten the STT finalize tail ("caller stopped speaking" → final transcript) — the biggest remaining mouth-to-ear contributor. | Open |
| **TASK-BE-020** | Speed up the backend's first vetted sentence (streaming). Second latency lever. | Open |
| **TASK-WEB-035** | Same STT finalize optimization, specifically on the WebSocket transport. | Open |
| **TASK-WEB-040** | Instrument the only still-unmeasured WS latency slice (`channel_ingress`, mic input) to complete the latency report. | Planned (Low) |

## Infra / deploy / resilience

| Ticket | Objective (the why) | State |
|---|---|---|
| **TASK-OPS-010** | Drain active sessions cleanly before recreating a container on deploy (don't cut a live call). Unblocks BUG-018's last third. | Planned (P1) |
| **TASK-INFRA-005** | Keep a WebRTC session routed to the same bridge (signaling stickiness at the LB) — negotiation breaks otherwise with 2 bridges. | Deferred — validate live |
| **TASK-BE-023** | Close unauthenticated ops surface (`/swagger-ui`, `/v3/api-docs`, `/actuator/metrics`) before external exposure. | Ready/Scheduled |
| **TASK-BE-030** | If Redis (shared memory) fails, fall back to local memory and stay in service instead of dropping out of rotation. | Planned |
| **TASK-BE-026** | Retry idempotent reads + circuit-break (resilience4j) when an upstream is down. | Deferred |
| **TASK-BE-031** | Reduce personal data sent to cloud providers (STT/TTS/LLM) — engineering piece of the OQ-009 compliance work. | Planned |
| **TASK-BE-057** | Refine the vague-billing-opener detector (false positives/negatives) after the BUG-025 fix. | Open (follow-up) |

## Open questions (product gates)

| Item | Objective (the why) |
|---|---|
| **OQ-006** | Prove Genesys on a real tenant (reachability/TLS, native barge-in/EOT events, Architect fail-safe). Blocks Genesys prod go. |
| **OQ-008** | Arbitrate the cross-domain retrieval top-k trade-off (voice is cross-domain by design → noise risk). |
| **OQ-009** | Inventory PII, retention, redaction before any real-customer traffic. Major compliance gate. |
