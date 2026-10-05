# Adversarial Code Review — BUG-028 (eir B2C parser null code → comparison collapses same-category lines)

- **Scope:** `fix/BUG-028-eir-b2c-parser-line-code`
- **Change:** `EirInvoiceText.slug` (new), `EirInvoiceBodyReader` (emit stable invoice-unique slug `code`),
  `InvoiceComparisonService.index()` (never drop a colliding line), E2E assertions flipped to residual 0,
  new unit tests.
- **Reviewer:** adversarial-code-review skill
- **Date:** 2026-10-05

## Verdict

Proceed.

## Satisfaction Score

Score: 94/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | The line `code` couples the comparison key to label wording. If a future eir layout renames a recurring product between months, the slug changes and the line becomes DISAPPEARED+APPEARED instead of CHANGED (still fully attributed to its category cause, residual stays 0, but the narrative loses the "same product moved" nuance). | `EirInvoiceBodyReader.uniqueCode` slugs the label | Acceptable for V1 (eir labels are stable). Revisit if a product-id token becomes available in the PDF. |
| Low | `index()` disambiguation key uses `#N`; the eir parser already guarantees uniqueness, so this path is only hit by other sources. Not covered by an eir end-to-end case (covered by a focused domain test instead). | `InvoiceComparisonServiceTest.never_drops_a_second_line_that_shares_a_matching_key` | Fine — the domain test is the right level for the generic safeguard. |
| Info | `slug` folds every non-`[a-z0-9]` run (incl. accents like `é`) to `-`. eir B2C labels are ASCII, so no collision observed; a future accented label could over-collapse. | `EirInvoiceText.NON_ALNUM` | Monitor if non-ASCII labels appear; add Unicode normalization then. |

## Story Coverage

| Acceptance criterion (BUG-028) | Covered? | Evidence |
|---|---|---|
| Same-category lines are no longer collapsed; each contributes to the diff | Yes | `EirB2cBillingComparisonE2eTest` (OPTION_CHANGE €16.98), `InvoiceComparisonServiceTest.never_drops…` |
| 99224964 Sep vs Aug: +€55.47 fully attributed, residual €0.00 | Yes | `EirB2cBillingComparisonE2eTest` |
| Parsed lines carry a stable, invoice-unique code; recurring product stable across months; prorata distinct | Yes | `EirInvoiceTextTest` (slug contract), reader `uniqueCode` |
| No line is ever silently dropped by the comparison index | Yes | hardened `index()` + domain regression test |
| Defaults and the fixture path are unchanged | Yes | full suite 710 green; parsing test ignores codes by design |

## Test Evidence

- Developer tests: `EirInvoiceTextTest` (4), `InvoiceComparisonServiceTest.never_drops_a_second_line_that_shares_a_matching_key` (1), `EirB2cBillingComparisonE2eTest` flipped to residual 0 / OPTION_CHANGE €16.98. Full backend suite **710** + ArchUnit green.
- Missing tests: none required. (`EirB2cRealPdfParsingTest` deliberately does not assert codes — unchanged.)
- QA scenarios to run: billing comparison for 99224964 on the real-PDF path (`bss.source=pdf`, `billrun.source=sample`, `pdf.source=eir-b2c`) → explanation accounts for the whole increase with no "unexplained" caveat.

## Observability And Latency

- Relevant slices: comparison (within the existing billing routing path).
- OpenTelemetry traces/metrics/logs: unchanged — this is a deterministic-correctness fix inside an
  already-instrumented path (`BackendTelemetry`), no new slice. No sensitive data added to logs.
- Missing: none.
- Risk: none (not a new runtime slice; no latency impact — same single-pass arithmetic).

## Security And Privacy

- Sensitive data risk: none — codes are derived from product labels (not account/PII); no new logging.
- Identity/access risk: none.
- Logging risk: none.

## Required Developer Actions

1. None (blocking list empty).

## Residual Risk If Accepted

- Label-derived codes are only as stable as the eir label wording (Low finding above). Acceptable for V1;
  revisit if a stable product identifier becomes available in the PDF or non-ASCII labels appear.
