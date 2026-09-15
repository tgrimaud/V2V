# BUG-020 — A listed-but-unfetchable invoice throws HTTP 500 instead of escalating

- **Severity:** Medium
- **Priority:** P2
- **Status:** Fixed (fix/BUG-020-billing-unfetchable-invoice-500)
- **Found by:** Adversarial review of the billing domain (Sprint 14, alongside BUG-019)
- **Area:** `com.voicesupport.billing.domain.service.BillingExplanationService`

## Problem

`BillingExplanationService.compareTwoMostRecent(...)` fetched each of the two most-recent
invoices via `bss.fetchInvoice(...).orElseThrow(() -> new IllegalStateException(...))`. When a
listed invoice could not be fetched, the service threw `IllegalStateException`, which the global
handler surfaces as **HTTP 500** — an unhandled server error on the customer voice path instead of
a safe advisor hand-off.

A listed invoice can legitimately be unfetchable at fetch time:
- a BSS race (listed then archived/removed between the list and the fetch call);
- the **BR-002-1 ownership guard** (BE-047) dropping an invoice whose account does not match the
  requested account (`EirBssBillingAdapter.ownsInvoice` returns `Optional.empty()`).

In both cases the correct behaviour is a **fail-closed escalation**, not a 500.

Note: a transient *network* failure still throws `RestClientException` in the adapter and is
correctly mapped to HTTP 503 by the global handler — that path is unchanged. This bug is only about
the **empty-Optional** ("listed but not fetchable / ownership mismatch") case.

## Root cause

The fetch helper mapped an empty `Optional<Invoice>` to a thrown exception. Empty-Optional is a
domain-expected outcome (not-found / ownership-dropped), so it must degrade gracefully rather than
escalate to an unhandled error.

## Fix

`compareTwoMostRecent(...)` now returns `Optional<InvoiceComparison>`: if either invoice fetch is
empty, it returns `Optional.empty()` and `explainForAccount(...)` maps that to
`BillingExplanation.notEnoughData(...)` — the same **safe escalation** already used for the
single-invoice / unusable-pair cases (NOT_ENOUGH_DATA, `escalate=true`,
`CODE_BILLING_UNEXPLAINED`). No exception, no 500.

## Test coverage

- New regression test `a_listed_but_unfetchable_invoice_escalates_instead_of_failing_with_a_500()`
  in `BillingExplanationServiceTest`: a `BssBillingPort` that lists two invoice summaries but always
  returns `Optional.empty()` on `fetchInvoice` now yields `NOT_ENOUGH_DATA` + `escalate=true`
  instead of throwing.

## Acceptance criteria

- [x] A listed-but-unfetchable invoice escalates (NOT_ENOUGH_DATA) instead of throwing.
- [x] The BR-002-1 ownership-dropped invoice path degrades to escalation, not 500.
- [x] Transient network failures still map to HTTP 503 (unchanged).
- [x] Full backend suite green.
