# QA Functional And Latency Report — TASK-BE-045 (billing chain behind the answer engine)

Ticket: TASK-BE-045 — wire the deterministic billing chain behind the conversation
answer engine, exposed as `POST /api/conversation/billing-explain`.
Branch: `task/TASK-BE-045-wire-billing-chain` (off `feat/sprint-14-billing-identity`).
Date: 2026-09-11. QA owner: qa-functional-latency.

## Executive Summary

- **Overall readiness: GO** for merge into the sprint branch. The billing chain is
  functionally correct against the six fixture journeys, fail-closed on identity and
  insufficient evidence, and enforces DEC-002 (no fabricated amount ever spoken).
- **Main blockers: none.** The endpoint, seam, guardrail and escalation paths behave as
  specified; adversarial review scored 93/100 with no blocking finding.
- **Residual risks (non-blocking, tracked):**
  - The "unchanged bill" wording omits the absolute TTC total (fail-closed: risks an
    over-cautious block, never a wrong figure).
  - `invoiceId` is accepted but ignored — V1 always compares the two most recent invoices.
  - Confidence values are hardcoded (0.9 / 0.6) pending OQ-002 thresholds.
  - Real Galaxion BSS + PDF extraction are still mocked (BE-047 / real integration).

## Scope Tested

- **Ticket / story:** TASK-BE-045 (Sprint 14 — billing & identity). Feeds QA-019 (functional)
  and QA-020 (latency).
- **Channels:** text/API (`/api/conversation/billing-explain`). Voice reuses the same
  backend chain; no voice-runtime code in this ticket.
- **Providers / fakes:** `InMemoryBssBillingAdapter` + `InMemoryCustomerDirectoryAdapter`
  over `BssBillingFixtures` (6 journeys); real `OutputGuardrail`; fake `AnswerGeneratorPort`
  (LLM). Real chain end-to-end otherwise (identity → comparable-invoice → BSS fetch →
  comparison → confidence gate → composer → seam → answer service).
- **Environment:** `mvn test` on JDK 25, no DB, no Ollama, no network (domain + application
  units and Cucumber BDD).

## Functional Results

| Area | Status | Evidence | Notes |
|---|---|---|---|
| Grounded increase explanation (discount expiry) | Pass | `billing-explanation.feature` #1; `BillingExplanationServiceTest` | LLM rephrases only the computed "+5.00 €"; grounded, no escalation |
| DEC-002 — never voice an uncomputed amount | Pass | feature #2; `BillingAnswerServiceTest` (block→escalate) | Guardrail blocks "99,00 €" absent from evidence → hand-off, LLM output discarded |
| Identity unresolved (unknown reference) | Pass | feature #3; `BillingExplanationServiceTest` | Asks to identify, no amount revealed, escalates `IDENTITY_UNVERIFIED` |
| Ambiguous reference never guesses account | Pass | feature #4 (`EIR-DUP`) | Fail-closed BR-002-1; no billing data leaked |
| Too little history (single invoice) | Pass | feature #5 (`EIR-1005`) | Escalates `BILLING_UNEXPLAINED`, no fabricated cause |
| Unusable invoice pair (no billable lines) | Pass | feature #6 (`EIR-1006`) | Escalates `BILLING_UNEXPLAINED` |
| Unchanged bill | Pass | feature #7 (`EIR-1001`) | Grounded "identique", no escalation |
| Non-billing question redirected | Pass | feature #8 | LLM never called (`callCount==0`), no escalation |
| API-key gating on the new endpoint | Pass | `ProtectedEndpointsApiKeyTest.billingExplainRejectedWithoutKey` | 401 without key |
| By-reference escalation (no inline PII) | Pass | `BillingExplainController` handoff build; log review | `[BILLING-EXPLAIN]` log carries no transcript/reference |

BDD suite (`RunKnowledgeBddTest`): **44 scenarios, 0 failures** (36 pre-existing + 8 billing).
Full backend suite: **560 tests + 8 BDD-added = green**; ArchUnit + Spring context boot green.

## Latency Results

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| Deterministic billing chain (`billing`) | 2.5 µs | 6.4 µs | 17.6 µs | 100 000 | Warm | Mock BSS, in-memory; identity lookup + ≤2-line comparison + gate + compose |
| LLM wording | — | — | — | — | — | Not exercised in QA harness (fake LLM). Same Mistral path as `/answer`; governed by ADR-0018 / BE-020 levers |
| Channel / STT / TTS / RAG / vector search | n/a | n/a | n/a | — | — | Not on this endpoint: billing evidence is deterministic (no vector search); text endpoint, no media |

Reading: the added `billing` slice is **negligible** (microseconds on mock BSS). The dominant
cost for an *answerable* turn stays the LLM wording slice, which is unchanged from the existing
`/answer` path — so BE-045 introduces no new mouth-to-ear latency risk. Real-BSS/PDF latency
(BE-047) must be re-measured on the `voice_support.slice{slice=billing}` timer once the live
adapter lands.

Correlation-id continuity: the controller sets the correlation id + channel on the MDC and
echoes the `X-Correlation-Id` header; the `billing` slice is tagged with the outcome
(`explained`/`partially_explained`/`identity_unresolved`/`not_enough_data`/`not_a_billing_request`/`error`).

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| `BillingIntentDetector` | Pass | Accent/diacritic-folded word-boundary match; no false hit on "demain" | — |
| `BillingExplanationComposer` | Pass | Deterministic FR/EN; every amount formatted from minor units | Add absolute TTC on unchanged wording (follow-up) |
| `BillingExplanationService` | Pass | Fail-closed on intent/identity/`<2 invoices`; two-most-recent comparison | invoiceId targeting (follow-up) |
| Seam (`BillingExplanationPort` + `InProcBillingExplanationAdapter`) | Pass | Mirrors the knowledge ACL; records `billing` slice by outcome | — |
| `BillingAnswerService` + `OutputGuardrail` | Pass | DEC-002 enforced by construction; LLM only rephrases | — |
| Escalation (`IDENTITY_UNVERIFIED`, `BILLING_UNEXPLAINED`) | Pass | By-reference hand-off, no inline PII (ADR-0019/DEC-013) | — |
| Observability | Pass | `billing` slice + correlation id + sanitized logs | Re-measure with real BSS (BE-047) |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Low | Unchanged wording omits absolute TTC total | Cosmetic; fail-closed | Backend (follow-up) |
| Low | `invoiceId` accepted but ignored | V1 uses two most recent; no correctness impact | Backend (follow-up) |
| Low | Hardcoded confidences (0.9 / 0.6) | Confidence signal not calibrated | OQ-002 |
| Info | Mock BSS/PDF only | Latency + parsing unproven on real data | BE-047 |

No functional defect requiring a bug ticket was found.

## Open Questions

- **Product:** confidence thresholds and whether "unchanged" should state the current total
  (OQ-002).
- **Architecture:** routing billing from `/converse` (D3a) — separate follow-up ticket.
- **Technical:** real Galaxion BSS + PDFBox extraction contract (BE-047).

## Recommendation

- **Go / No-go: GO** — BE-045 is functionally accepted and latency-safe on the fixture stack.
- **Required fixes before pilot:** none for this ticket. Before *real* billing goes live:
  BE-047 (live BSS/PDF) + re-measured `billing` slice + confidence calibration (OQ-002).
