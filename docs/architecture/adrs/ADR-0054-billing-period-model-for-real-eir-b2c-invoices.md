# ADR-0054: Billing period model for real eir B2C invoices (usage/charge date ranges + line periods)

## Status

Accepted (2026-09-29)

## Context

The V1 billing model represented an invoice period as `BillingPeriod(id, invoiceDate)` — a stable
id plus a single date. Validating the model against **real anonymized eir B2C invoices** (three
accounts × two consecutive bill runs — see `docs/integrations/galaxion/eir-b2c-invoice-samples.md`)
surfaced two concrete problems and confirmed a structural mismatch:

1. **Ordering bug (functional).** `ComparableInvoiceService` picks *current* vs *previous* by
   sorting summaries on `invoiceDate` descending, tie-broken by invoice id ascending. On the real
   invoices the printed **"Billing date" is identical** across the August and September bill runs
   (25 Sep 26), so `invoiceDate` cannot order them; the id tie-break then places the **older** run
   (`2608…`) first, making August the "current" invoice. The reliable ordering axis is the
   **bill-run month = usage-period start** (12 Aug vs 12 Sep), also encoded in the bill number
   (`2608…`/`2609…`) and the file name (`20260812`/`20260912`).

2. **No per-line period.** `InvoiceItem`/`InvoiceGroup` carry no period, yet each real invoice
   states a period per block (`Subscription and options for the period from X to Y`) and, crucially,
   **proratas** carry an explicit sub-window (`eir TV from 25 Sep 26 until 11 Oct 26 11.33`). A
   prorata is a central discrepancy cause; without a line period it can only live as free text in
   `Evidence`.

3. **Three period notions.** Each invoice exposes an **issue date** ("Billing date"), a **usage
   period** (the consumption / one-time window — the customer's "this month"), and a **monthly
   charge period** (the forward window recurring subscriptions are billed in advance for). A single
   date cannot hold them.

The target extraction contract (`docs/integrations/galaxion/invoice-extraction-json.md`) already
anticipates `invoice.period.start/end` and per-line `period.start/end`, so this change aligns the
domain model with the contract.

## Decision

1. Introduce an immutable value object **`DateRange(start, end)`** (ordering validated at
   construction: `end >= start`), reused at invoice **and** line level rather than duplicating
   `start`/`end` fields.

2. Extend **`BillingPeriod`** to `(id, invoiceDate, DateRange usagePeriod, DateRange chargePeriod)`:
   - `id` — stable bill-run reference (invoice number).
   - `invoiceDate` — the issue/"Billing date", kept for audit and display; **no longer the ordering
     key**.
   - `usagePeriod` — customer-facing "this month" window; the **canonical ordering/labeling axis**
     via a new `orderingDate()` (usage-period start when present, else `invoiceDate`).
   - `chargePeriod` — forward window for recurring charges billed in advance.
   - **Both ranges are nullable** (kept flexible): a partially-extracted invoice, or a source that
     does not expose a window, is still representable. A **backward-compatible secondary constructor**
     `BillingPeriod(id, invoiceDate)` delegates with null ranges so existing call sites are untouched.

3. Add a nullable **`DateRange period`** to `InvoiceItem` and `InvoiceGroup` (the item-level period
   is the must-have for proratas; the group-level period reflects the block header). Both records
   keep a backward-compatible secondary constructor without the period.

4. Change `ComparableInvoiceService` ordering to `orderingDate()` descending, tie-broken by invoice
   id ascending (unchanged tie-break), fixing the current/previous inversion on real data.

5. **Comparison matching is unchanged** in this ADR: lines are still matched by label/code, not by
   period. The line period is descriptive/explanatory for now (promoting it to a matching signal is a
   future option, not required here).

## Consequences

- The `BillingPeriod`/`InvoiceItem`/`InvoiceGroup` canonical signatures gain a field each, but the
  secondary constructors mean existing production and test call sites compile unchanged; only the new
  realistic fixtures use the richer form.
- Current/previous selection is now correct on real eir B2C invoices (regression-tested with an
  identical-issue-date pair).
- Proratas can be explained with their exact sub-period.
- `chargePeriod` is stored but **not yet consumed** by the explanation composer — recorded as a
  follow-up (answer wording for advance billing).
- Flexibility preserved: all new ranges are nullable, so future extraction paths can populate them
  progressively, and a later ADR can promote `usagePeriod` to required or add a line-period matching
  key without a rewrite.
- Pure value-object change: ArchUnit (hexagonal/boundary/naming) is unaffected; the domain stays
  framework-free.

## Alternatives Considered

- **Keep a single `invoiceDate` + periods as free text in `Evidence`** — rejected: the ordering bug
  remains and proratas stay unexplained/untyped.
- **Store only `usagePeriod` (drop `chargePeriod`)** — rejected for now: `chargePeriod` is cheap to
  store and needed to answer "why am I billed for next month in advance"; kept nullable so it costs
  nothing when absent.
- **A dedicated period entity per line with its own identity** — over-engineered for V1; a shared
  `DateRange` VO is sufficient.
- **Make the ranges required** — rejected: reduces tolerance to PARTIAL extractions and real-world
  variance; flexibility was an explicit goal.
- **Rename `invoiceDate` → `issueDate`** — rejected to avoid churn across the EIR adapter, its JSON
  mapping and several tests; the name keeps its meaning (the issue/"Billing date").

## Related Documents

- `docs/integrations/galaxion/eir-b2c-invoice-samples.md` (new — the validated real-invoice structure)
- `docs/integrations/galaxion/invoice-extraction-json.md` (target extraction contract)
- `docs/integrations/galaxion/bss-billing-data-model.md` (BSS hierarchy)
- ADR-0005 (invoice PDF extraction before LLM explanation)
- ADR-0052 (billing explanation behind the answer engine)
- TASK-BE-059
