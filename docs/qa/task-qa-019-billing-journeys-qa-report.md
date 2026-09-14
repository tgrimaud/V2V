# QA Functional And Latency Report — TASK-QA-019 (billing socle journeys)

Ticket: TASK-QA-019 — functional + latency acceptance over the six canonical billing fixture
journeys, exercised end-to-end through the answer engine (`POST /api/conversation/billing-explain`).
Branch: `task/TASK-QA-019-billing-journeys` (off `feat/sprint-14-billing-identity`).
Date: 2026-09-14. QA owner: qa-functional-latency. Complements the BE-045 QA report.

## Executive Summary

- **Overall readiness: GO.** All six fixture journeys have an explicit product-observable
  acceptance scenario; grounded journeys phrase only computed amounts (DEC-002), degraded
  journeys fail closed (identity / insufficient data) with a by-reference hand-off.
- **Main blockers: none.**
- **Residual risks (non-blocking, tracked):** unchanged-bill wording omits the absolute TTC
  total; `invoiceId` accepted but ignored (V1 compares the two most recent); hardcoded
  confidences (OQ-002); real Galaxion BSS/PDF still mocked (BE-047 / QA-020).

## Scope Tested

- **Journeys:** the six `BssBillingFixtures` accounts — `eir-001` nominal, `eir-002` discount
  expiry, `eir-003` usage overage, `eir-004` proration, `eir-005` insufficient data (single
  invoice), `eir-006` unusable (no billable lines) — plus identity-unresolved, ambiguous
  reference, DEC-002 amount block, and non-billing redirect.
- **Channel:** text/API (`/api/conversation/billing-explain`); the same backend chain backs voice.
- **Providers / fakes:** in-memory BSS + customer directory over fixtures; real `OutputGuardrail`;
  fake `AnswerGeneratorPort` (LLM). Whole chain otherwise real.
- **Automation:** Cucumber for Java — `billing-explanation.feature` (10 scenarios), suite
  `RunKnowledgeBddTest` = **46 scenarios green**. **Behave: N/A** (no Python voice-runtime
  billing behavior; reserved for STT/TTS/turn/barge-in).
- **Environment:** `mvn test` on JDK 25, no DB / Ollama / network.

## Functional Results — Journey Matrix

| # | Fixture (account) | Cause type | Δ (TTC) | Expected outcome | Status |
|---|---|---|---:|---|---|
| 1 | nominal (`eir-001`) | — | 0 | Grounded "bill unchanged", no escalation | Pass |
| 2 | discount expiry (`eir-002`) | `DISCOUNT_EXPIRY` | +5.00 € | Grounded increase (fin de remise), no escalation | Pass |
| 3 | usage overage (`eir-003`) | `USAGE_OVERAGE` | +12.00 € | Grounded increase (dépassement), no escalation | Pass |
| 4 | proration (`eir-004`) | `PRORATION` | +8.00 € | Grounded increase (prorata), no escalation | Pass |
| 5 | insufficient data (`eir-005`) | — (1 invoice) | n/a | Escalate `BILLING_UNEXPLAINED`, no fabricated cause | Pass |
| 6 | unusable (`eir-006`) | — (no lines) | n/a | Escalate `BILLING_UNEXPLAINED` | Pass |

Cross-cutting behaviors:

| Behavior | Expected | Status |
|---|---|---|
| DEC-002 amount grounding | LLM amount absent from evidence → blocked → advisor hand-off | Pass |
| Identity unresolved (unknown ref) | Ask to identify, no amount revealed, escalate `IDENTITY_UNVERIFIED` | Pass |
| Ambiguous reference (`EIR-DUP`) | Never guess account, escalate identity fail-closed (BR-002-1) | Pass |
| Non-billing question | Redirect without calling the LLM, no escalation | Pass |
| API-key gating | 401 without key (`ProtectedEndpointsApiKeyTest`) | Pass |
| By-reference escalation | Hand-off carries no inline PII (ADR-0019 / DEC-013) | Pass |

## Latency Results

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| Deterministic billing chain (`billing`) | 2.5 µs | 6.4 µs | 17.6 µs | 100 000 | Warm | Mock BSS, in-memory (BE-045 probe) |
| LLM wording | — | — | — | — | — | Not exercised in QA harness (fake LLM); same Mistral path as `/answer` (ADR-0018) |
| Channel / STT / TTS / RAG / vector search | n/a | n/a | n/a | — | — | Not on this endpoint (deterministic evidence, text) |

The `billing` slice is negligible; the dominant answerable-turn cost stays the (unchanged)
LLM wording. Real-BSS/PDF latency must be re-measured on `voice_support.slice{slice=billing}`
once the live adapter lands (BE-047). Correlation-id continuity verified via the controller
(`X-Correlation-Id` echo + MDC channel), slice tagged by outcome.

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| `BssBillingFixtures` | Pass | Six journeys load and drive all scenarios; consistent tax split/roll-up | — |
| `InvoiceComparisonService` + `ComparisonConfidenceService` | Pass | Overage/proration fully attributed (residual 0 → EXPLAINABLE) | — |
| `BillingExplanationComposer` | Pass | Grounded FR wording per cause; every amount from computed comparison | Absolute TTC on unchanged wording (follow-up) |
| End-to-end chain (endpoint → seam → answer) | Pass | 46 BDD scenarios green | — |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Low | Unchanged wording omits absolute TTC total | Cosmetic; fail-closed | Backend (follow-up) |
| Low | `invoiceId` accepted but ignored | V1 uses two most recent | Backend (follow-up) |
| Low | Hardcoded confidences (0.9 / 0.6) | Confidence not calibrated | OQ-002 |
| Info | Mock BSS/PDF only | Latency + parsing unproven on real data | BE-047 / QA-020 |

No functional defect requiring a bug ticket was found.

## Open Questions

- **Product:** confidence thresholds; whether "unchanged" should state the current total (OQ-002).
- **Architecture:** routing billing from `/converse` (D3a follow-up).
- **Technical:** real Galaxion BSS + PDFBox extraction (BE-047), then real-data QA (QA-020).

## Recommendation

- **Go / No-go: GO.** The billing socle is functionally accepted across the six journeys and
  latency-safe on the fixture stack.
- **Required before real billing goes live:** BE-047 (live BSS/PDF) + re-measured `billing`
  slice + confidence calibration (OQ-002); real-data validation is QA-020.
