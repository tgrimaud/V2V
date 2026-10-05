# Adversarial Code Review — TASK-BE-067 (service added/removed is a named billing cause)

- **Scope:** `task/TASK-BE-067-subscription-service-change-cause`
- **Change:** `BillingCauseType` (+`SERVICE_ADDED`, `SERVICE_REMOVED`), `InvoiceComparisonService.cause(category, kind)`,
  `BillingExplanationComposer` wording (FR/EN), tests updated/added, ADR-0003 amended.
- **Reviewer:** adversarial-code-review skill
- **Date:** 2026-10-05

## Verdict

Proceed.

## Satisfaction Score

Score: 93/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | "Service added/removed" is inferred purely from a `SUBSCRIPTION` line appearing/disappearing. A re-plan that swaps one subscription product for another (old DISAPPEARED + new APPEARED, same service) would read as one removed + one added rather than a single "plan change". | `InvoiceComparisonService.cause` | Acceptable for V1 (the voiced causes are still correct and reconcile to €0 residual). Revisit if plan-swap wording is desired. |
| Low | A `SUBSCRIPTION` line whose amount merely CHANGED in place is still `UNEXPLAINED` by design — correct, but means a legit mid-contract subscription price change still escalates. | `cause(...) default -> UNEXPLAINED`; `ComparisonConfidenceServiceTest.a_delta_attributed_only_to_the_unexplained_bucket_escalates` | Intended (BR-003 fail-closed). Out of scope. |
| Info | Enum order places `SERVICE_ADDED`/`SERVICE_REMOVED` after `OPTION_CHANGE`; this drives the order causes are voiced. | `BillingCauseType` | Fine — reads naturally (options, then service add/remove, then prorata/one-off). |

## Story Coverage

| Acceptance criterion (TASK-BE-067) | Covered? | Evidence |
|---|---|---|
| An appearing subscription (new service) → named cause, not residual | Yes | `InvoiceComparisonServiceTest.a_new_subscription_line_is_attributed_to_service_added`; E2E 99226126/99226337 residual €0.00 |
| A disappearing subscription (removed service) → named cause | Yes | `InvoiceComparisonServiceTest.a_removed_subscription_line_is_attributed_to_service_removed` |
| An in-place CHANGED subscription stays UNEXPLAINED (escalates) | Yes | `ComparisonConfidenceServiceTest.a_delta_attributed_only_to_the_unexplained_bucket_escalates`; `InvoiceComparisonServiceTest.an_opaque_in_place_subscription_change_…` |
| The explanation voices the new cause (FR/EN), grounded | Yes | `BillingExplanationComposerTest.voices_a_new_service_when_a_subscription_appears` |
| Deterministic, no LLM; non-subscription causes unchanged | Yes | pure `switch` on `ChangeKind`; `CAUSE_BY_CATEGORY` untouched; full suite 715 green |

## Test Evidence

- Developer tests: +`SERVICE_ADDED`/`SERVICE_REMOVED` domain tests, re-modelled the opaque-change test to a CHANGED subscription (×2: comparison + confidence), composer FR/EN wording test, E2E flipped to residual €0.00 for both multi-service accounts. Full backend suite **715** + ArchUnit green.
- Missing tests: none required.
- QA scenarios to run: billing comparison for 99226126 / 99226337 on the real-PDF path → the explanation names the new service and reports no "unexplained" part.

## Observability And Latency

- Relevant slices: comparison (within the already-instrumented billing routing). No new slice.
- OpenTelemetry traces/metrics/logs: unchanged — deterministic correctness/semantics change inside an instrumented path; no sensitive data added.
- Missing: none. Risk: none (same single-pass arithmetic; residual now lower for multi-service accounts → fewer false escalations).

## Security And Privacy

- Sensitive data risk: none — causes derive from category + change kind, no PII.
- Identity/access risk: none.
- Logging risk: none.

## Required Developer Actions

1. None (blocking list empty).

## Residual Risk If Accepted

- Plan-swap is voiced as a remove+add pair rather than a single "plan change" (Low finding). Acceptable for V1; residual still reconciles to €0.
