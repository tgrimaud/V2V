# Adversarial code review — BUG-020 (listed-but-unfetchable invoice → 500)

- **Branch:** `fix/BUG-020-billing-unfetchable-invoice-500`
- **Reviewed:** 2026-09-15
- **Scope:** `BillingExplanationService` fetch-failure degraded mode + regression test.

## Verdict

Proceed.

## Satisfaction Score

Score: 95/100
QA gate: Pass

## Blocking Findings

None.

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | Unused `InvoiceId` import left after removing the `fetch` helper | `BillingExplanationService` line 12 | **Fixed** during review — import removed, 582 tests still green. |
| Info | `notEnoughData` covers both "single invoice", "unusable pair" and now "unfetchable" — the escalation reason is not distinguishable in telemetry | `outcome=not_enough_data` for all three | Acceptable for V1 (all three are the same safe hand-off). Consider a finer `reason` attribute if Ops needs to separate BSS-race/ownership-drop from genuine no-data later. |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| Listed-but-unfetchable invoice escalates instead of throwing | Yes | `a_listed_but_unfetchable_invoice_escalates_instead_of_failing_with_a_500()` → `NOT_ENOUGH_DATA` + `escalate=true` |
| BR-002-1 ownership-dropped invoice degrades to escalation, not 500 | Yes | Same empty-Optional path the ownership guard produces |
| Transient network failures still map to HTTP 503 | Yes | `RestClientException` → 503 in `GlobalExceptionHandler` (unchanged; adapter still throws on network error) |
| Full backend suite green | Yes | 582 tests, 0 failures, 0 errors |

## Test Evidence

- Developer tests: 1 new regression test with a `BssBillingPort` that lists two invoices but always returns `Optional.empty()` on fetch.
- Missing tests: none blocking.
- QA scenarios to run: none new required; existing NOT_ENOUGH_DATA voice hand-off scenario covers the customer-visible behaviour.

## Observability And Latency

- Relevant slices: `billing` (whole-chain), `bss` (network hop, BE-047).
- Structured logs: `[TELEMETRY] slice=billing outcome=not_enough_data` still emitted on the degraded path (verified in the test run).
- Metrics: `voice_support.slice{slice=billing,outcome=not_enough_data}` continues to record — degraded turn is not silent.
- Missing: none for this change.
- Risk: none.

## Security And Privacy

- No sensitive data added to logs. Empty-Optional path carries no invoice content.
- Identity/access: the fix *reinforces* BR-002-1 — an ownership-dropped invoice now degrades to escalation instead of a 500 that could hint at existence.

## Required Developer Actions

None outstanding (the single low finding was fixed during review).

## Residual Risk If Accepted

- Telemetry cannot yet distinguish an unfetchable/ownership-dropped escalation from a genuine
  not-enough-data escalation. Low operational impact for V1; can be refined with a `reason`
  attribute if needed.
