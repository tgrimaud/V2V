# Adversarial Code Review — TASK-BE-047 (Eir BSS adapter, enquiry path)

- **Scope:** first slice of the real read-only `BssBillingPort` over the two Eir services
  (`billing-enquiry-service` 3.1.0 + `billing-service` 2.3.1), config-selected (`source=mock` default → `eir`).
- **Branch:** `task/TASK-BE-047-eir-bss-adapter` · commits `d376dbb` (adapter) + `5e5d816` (BSS observability fix).
- **Reviewer skill:** `.cursor/skills/adversarial-code-review`.
- **Date:** 2026-09-14.

## Verdict

**Proceed** for merge of this slice **with `source=mock` default** (the `eir` path is not runtime-active).
Enabling `source=eir` stays **blocked** by the three required actions below (residuals accepted, tracked for QA-020).

## Satisfaction Score

**Score: 91/100 — QA gate: Pass** (mock-default slice).

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| High | Real BSS network hop not observable — the upstream `billing` slice hid BSS latency | initial `EirBssBillingAdapter` had no `BackendTelemetry` | ✅ Fixed: `slice=bss`, `provider=eir`, outcome + `[TELEMETRY]` log (`5e5d816`), timer assertion in test |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| High (blocks `eir`) | BR-002-1 not enforced on `fetchInvoice` — the enquiry invoice is not verified to belong to the requested account | `toInvoice()` ignored `dto.accountId()` | ✅ **Fixed (2026-09-15)**: account-id linkage confirmed (billing-service `account_id` == enquiry `billingAccountId`); `ownsInvoice()` compares the returned owner to the requested account and fails closed. Test: `fetchInvoice_failsClosedWhenInvoiceBelongsToAnotherAccount` |
| Medium | Reconciliation assumption `invoiceAmount = recurring+oneOff+usage+vat` | `totals()` sets `taxIncluded=invoiceAmount`, lines = 4 buckets | Any gap (credits/adjustments) → residual → confidence gate → escalate (fail-closed). Validate on a real sample |
| Medium | EUR default + `usageAmount→OVERAGE` + `recurring→SUBSCRIPTION` coded defaults | `EirBssBillingAdapter` | Confirm currency on a real payload; undetailed `recurring` → discount/option/proration deltas surface as `UNEXPLAINED` (fail-closed) until the CSV `detail-report` is mapped |
| Low | Server-side upstream-error logs may contain the BSS response body | `GlobalExceptionHandler.handleUpstream` logs full `ex`; client sees generic `ERR_UPSTREAM` | Acceptable (server-only); watch for invoice data in logs during QA |

## Story Coverage

| Criterion | Covered? | Evidence |
|---|---|---|
| Real adapter behind `BssBillingPort` | ✅ | `EirBssBillingAdapter implements BssBillingPort` |
| Independent per-service port implementations | ✅ | two seams (`BillingEnquiryClient` / `BillingServiceClient`), two REST adapters |
| No external type leaks past the adapter | ✅ | DTOs nested, domain-only mapping |
| Config-selected, no regression | ✅ | `source=mock` default, 577 tests green, context boot OK |
| Structured source first (PDF fallback) | ✅ | enquiry breakdown → domain; PDF/CSV = follow-up |

## Test Evidence

- **Developer tests:** `EirBssBillingAdapterTest` (4 — mapping, reconciliation, fail-closed: non-numeric id /
  not-found / skip unusable, + `bss` slice assertion); `EirBillingJsonMappingTest` (2 — camelCase under SNAKE_CASE).
  ArchUnit (`NamingConventions`, `Hexagonal`) + Spring context boot green. Full backend suite: 577 / 0 / 0.
- **Missing tests:** 5xx transport → 503 propagation (covered by the `RestClient` contract, not unit-tested);
  BR-002-1 ownership check (to add with the fix).
- **QA scenarios to run (QA-020, real data):** cents/pence, real `details`/CSV shape, account-id typing, line
  catalogue, real BSS latency (the `bss` slice is now measurable).

## Observability And Latency

- **Slices:** `bss` (new) per hop, distinct from `billing`.
- **Traces/Metrics:** `voice_support.slice{slice=bss,provider=eir,outcome}` → p50/p95/p99.
- **Structured logs:** `[TELEMETRY] slice=bss …` with correlation_id + outcome + duration_ms.
- **Missing:** none for this slice; real volume to be collected in QA-020.

## Security And Privacy

- **Sensitive data:** `Evidence` = category + amount (no PII); `galaxion-user-identifier` never logged (only `user-type`).
- **Identity/access:** account scope enforced by `listInvoices` (billing-service); `fetchInvoice` reinforcement = accepted residual (path inactive).
- **Logging:** upstream error body may reach server logs — watch in QA.

## Required Developer Actions (before `source=eir`)

1. ✅ **Done (2026-09-15):** BR-002-1 ownership check on `fetchInvoice` — id linkage confirmed (same space), fail-closed guard + test added.
2. ✅ **Done (2026-09-15, live account 5):** unit = **cents** confirmed; `invoiceId`==`invoiceNumber`; **mapping bug fixed** — `vatAmount` is inside the TTC total, not additive, so no separate TAX line; category lines reconcile to `invoiceAmount`.
3. **Blocked:** CSV `detail-report` (and PDF `summary-report`) return **HTTP 412 `archive-file-token-is-null`** — need the archive token before fine-grained cause attribution (discount/option/proration) can leave `UNEXPLAINED`. Also need a two-invoice account for a real delta (account 5 has one).

## Residual Risk If Accepted (mock-default merge)

- The `eir` path is not exercised at runtime (`mock` default) → no regression risk today; the three actions above
  are activation prerequisites, not merge prerequisites.
