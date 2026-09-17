# BUG-019 — A delta attributed only to the UNEXPLAINED bucket is marked "fully explained"

## Header

- **Bug ID:** BUG-019
- **Title:** Confidence gate treats UNEXPLAINED-cause amounts as explained (no escalation, contradictory wording)
- **Status:** Ready for adversarial review
- **Severity:** High
- **Priority:** P1
- **Detected by:** Adversarial review (billing domain)
- **Detected date:** 2026-09-15
- **Related user story:** US-005 / US-010–013 (billing explanation)
- **Related epic:** EPIC billing
- **Branch:** `fix/BUG-019-billing-unexplained-cause-gate`
- **Owner:** Backend developer

## Problem Statement

When the whole invoice delta falls into the `UNEXPLAINED` cause bucket (e.g. a bare
`recurringAmount`/subscription move — the coarse Eir case, or an unmapped/`OTHER`/`PAYMENT` line),
the comparison reported a **zero residual**, the confidence gate returned **EXPLAINABLE (0.9, no
escalation)**, and the composer voiced *"your bill increased by X. This is due to an unexplained
part (+X)."* — a fully-confident, contradictory answer that should have escalated.

## Root Cause

`InvoiceComparisonService` computed `unexplainedAmount = totalDelta − Σ(all line deltas)`, i.e. only
the **arithmetic** gap between the header total and the matched lines. An amount attributed to the
`UNEXPLAINED` **cause** was counted as "explained" (it is a present line), so it never reached the
residual the `ComparisonConfidenceService` gate keys off. The mock fixtures (`eir-001..006`) use only
fine categories (`DISCOUNT`/`USAGE`/`PRORATA`…), so the defect was masked in tests — but the real Eir
enquiry breakdown maps `recurringAmount → SUBSCRIPTION → UNEXPLAINED`, which is the most common case.

## Reproduction Steps

1. Given two invoices whose only difference is a `SUBSCRIPTION` (or `OTHER`/`PAYMENT`) line moving by +500.
2. When `InvoiceComparisonService.compare` then `ComparisonConfidenceService.assess` run.
3. Then (before fix) `unexplainedAmount = 0`, confidence `EXPLAINABLE`, `escalate = false`.

## Expected Result

A change not attributed to an identified business cause is surfaced as **residual** and, above the
tolerance, escalates (`INSUFFICIENT` / `RESIDUAL_TOO_HIGH`); the composer never claims it is explained.

## Actual Result

`EXPLAINABLE` with 0.9 confidence, no escalation, wording "explained by an unexplained part".

## Fix

`InvoiceComparisonService`:
- `causes()` no longer emits the `UNEXPLAINED` bucket as a business cause (it is not a cause).
- `unexplainedAmount = totalDelta − Σ(contributions of identified causes only)`, so `UNEXPLAINED`-category
  amounts stay in the residual (BR-003 — always surfaced) and the gate can escalate them.
- `lineDeltas` still exposes every line change (full transparency); only the *cause promotion* changed.

## Impact

- **Customer:** would have been told a bill change was fully understood when it was not (over-stated
  certainty), instead of being handed to an advisor. Highest risk on the real Eir coarse breakdown.
- **Security/privacy:** none.
- **Pilot-readiness:** blocked enabling `source=eir` with trustworthy explanations.

## Acceptance Criteria For Fix

- [x] The defect no longer reproduces.
- [x] A regression test covers the failure (`InvoiceComparisonServiceTest.an_unexplained_category_line_is_not_a_cause_and_becomes_the_residual`, `ComparisonConfidenceServiceTest.a_delta_attributed_only_to_the_unexplained_bucket_escalates`).
- [x] OpenTelemetry: not applicable (pure domain; slices unchanged).
- [ ] Adversarial code review at least 90% satisfied.
- [ ] QA retest passes.
- [x] Backlog/docs updated (this ticket; billing review note).

## Developer Notes

- **root cause:** residual computed from arithmetic gap only, ignoring UNEXPLAINED-cause amounts.
- **files changed:** `InvoiceComparisonService.java`; tests `InvoiceComparisonServiceTest`, `ComparisonConfidenceServiceTest`.
- **tests added/updated:** 2 rewritten to use an identified cause line, 2 regression tests added.
- **OpenTelemetry added/updated:** none (pure domain).
- **residual risk:** a mixed delta with a small UNEXPLAINED part below tolerance is still PARTIAL (voiced with a caveat) — intended.

## QA Retest

- **Retested by:**
- **Retest date:**
- **Scenarios rerun:**
- **Result:**
- **Retest evidence:**

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:**
