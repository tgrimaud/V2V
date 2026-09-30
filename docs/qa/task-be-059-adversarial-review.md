# Adversarial code review — TASK-BE-059 (eir B2C invoice model validation + realistic mock)

**Branch:** `task/TASK-BE-059-eir-b2c-period-model-and-mock`
**Reviewed:** 2026-09-29
**Decision:** ADR-0054
**Skill:** `.cursor/skills/adversarial-code-review`

## Verdict

**PASS — 93/100.** No blocking findings. The change is a backward-compatible value-object extension
plus data fixtures and docs; the full backend suite (652) and ArchUnit pass. Two residuals accepted.

## Satisfaction Score: 93/100

| Dimension | Score | Notes |
|---|---:|---|
| Story coverage | 19/20 | A (validation doc) + B (realistic mock) + C (model evolution) all delivered; period discussed and settled before implementation as requested. |
| Correctness | 19/20 | Ordering bug reproduced + fixed; all six invoices reconcile exactly; regression test locks the identical-issue-date case. |
| Tests | 19/20 | New `DateRangeTest`, `EirB2cSampleFixturesTest` (per-invoice TTC reconciliation + published totals), ordering regression. Manual fakes, GIVEN/WHEN/THEN. |
| Architecture / guidelines | 17/20 | Pure-domain VO, hexagonal boundaries intact, backward-compatible ctors. One class over the 200-line budget (data fixtures). |
| Docs / observability | 19/20 | ADR-0054 + validation doc + ticket/index/ledger; not runtime-affecting on the voice path. |

## Blocking findings

None.

## Non-blocking / Low findings

| # | Severity | Finding | Disposition |
|---|---|---|---|
| L1 | Low | `EirB2cSampleFixtures` is 223 lines, over the 200-line class budget. | **Residual accepted** — cohesive pure test data for one source (eir); no branching logic. Split per-account only if a second real source is added. |
| L2 | Low | Per-line VAT is synthetic (23% derivation); the real PDF has no per-line tax. | Documented (G1). Comparison basis is TTC (exact); HT/VAT are audit-only. |
| L3 | Low | `chargePeriod` stored on `BillingPeriod` but not consumed by the explanation composer. | Intentional follow-up (ADR-0054 Consequences); nullable, no behavior change. |
| L4 | Low | Mock customer directory resolves an account number to itself as reference. | Governed by OQ-001 / ADR-0050 (identity out of scope here); pilot-only mock. |

## Info

- I1: `DateRange`, line/group `period`, and both `BillingPeriod` ranges are **nullable** with
  secondary constructors — deliberate flexibility per the user directive ("garder une certaine
  souplesse si on doit le changer dans le futur"); zero churn on existing call sites.
- I2: `BssBillingFixtures` (synthetic eir-00X journeys, and its `containsExactlyInAnyOrder` test) is
  untouched — realistic data lives in a separate class merged at config time (`mockInvoices()`).

## Story coverage

- Validation (A): `docs/integrations/galaxion/eir-b2c-invoice-samples.md` — structure, answered open
  questions, three Aug→Sep deltas, gaps G1–G4.
- Realistic mock (B): six real invoices wired into the mock BSS + PDF fallback + customer directory.
- Model evolution (C): ADR-0054 (`DateRange`, `orderingDate()`, nullable line period, ordering fix).

## Test evidence

`cd backend && mvn test` → **652 tests, 0 failures**; ArchUnit (Hexagonal / ContextBoundary / Naming)
green. New tests: `DateRangeTest` (4), `EirB2cSampleFixturesTest` (5), `ComparableInvoiceServiceTest`
identical-issue-date ordering regression.

## Observability

Not runtime-affecting on the voice conversation path (billing explanation is behind the dedicated
billing endpoint, ADR-0052 D3c; not routed from `/converse`). Existing billing telemetry slice
unchanged. No new traces/metrics required.

## Security

No secrets, no new external calls, no PII beyond the anonymized test account numbers (invoice PDFs
are not committed). Read-only BSS port contract unchanged.

## Required actions

None (PASS). Residuals L1–L4 accepted and tracked in ADR-0054 / the ticket "Out Of Scope" section.

## Residual (accepted)

- L1 fixtures class > 200 lines (pure data).
- L3 `chargePeriod` + line period stored but not yet surfaced in customer-facing wording.
