# Galaxion / BSS — Coordination Request (Billing V1)

> Ticket: TASK-INFRA-017 · Sprint 14 (Billing Identity + BSS/PDF Evidence + Deterministic Comparison) · Status: **request ready to send**
> Audience: Galaxion / BSS billing owners + our backend/product team.

## 1. Purpose

We are building the V1 billing assistant: it explains to a customer **why an
invoice changed** by comparing two invoices with a **deterministic engine**
(amounts and causes computed by code; the LLM only phrases the confirmed, traceable
result — it never computes amounts). This document centralizes everything we need
from the Galaxion / BSS side to validate V1 against **real** data.

It groups, prioritizes and assigns an owner to the open items currently scattered
across `missing-inputs.md`, `bss-integration-plan.md`, `bss-billing-data-model.md`,
`galaxion-billing-contracts.md` and the V1 open questions (OQ-001/003/004). The
build does **not** wait on these answers (we start on fixtures + a BSS mock), but
**real-data acceptance does**.

## 2. What is already decided on our side (please do not re-answer)

- **Billing source = `billing-api` only** (`billing-service` is not used).
- **Prices are tax-included (TTC)** (confirmed 2026-09-09) → the customer-facing
  comparison basis is the tax-included amount (`amountTaxesIncluded` /
  `vat_incl_amount` / `vatIncTotal`); tax-excluded amounts are kept for audit only.
- **Access goes through a typed read-only port** (`BssBillingPort`, ADR-0004); we
  never mutate BSS data in V1.
- We already have the **real billing data model** you shared (2026-09-08):
  `invoice → invoice_section → invoice_group → invoice_item`, amounts at each level
  (`bss-billing-data-model.md`). It matches the shape of `ComposedInvoiceResponse`
  from `billing-api` — which drives request #1 below.

## 3. Requests (prioritized)

### P1 — Structured invoice-line source (biggest lever)

The data model you shared is a structured invoice tree. `billing-api` documents
`GET /invoices/composed` (`ComposedInvoiceResponse`: `sections[]`, `items[]`,
`taxes[]`, `amount`) and `GET /invoices/selected` (`SelectedInvoiceResponse`), whose
items carry `code`, `type`, `defaultPrice` (cents), `amount` (tax-excl/tax-incl),
`volume`, `percentage`, `effectiveAt`, `referencePeriod`, `effectivePeriod`.

**Question:** can `GET /invoices/composed` (or `/invoices/selected`) be the
**validated read-only structured source** for invoice lines?

**Why it matters:** if yes, our comparison engine consumes structured lines
directly and **PDF extraction becomes a fallback**, not the primary path — a major
reliability gain (no fragile PDF parsing on the critical path). Please confirm:

- which of the two (`composed` vs `selected`) is authoritative for a customer
  invoice, and the difference between them;
- one **anonymized example response** for a real invoice;
- whether every needed level is present (invoice total, sections, items) and stable
  month to month.

### P1 — Anonymized invoice PDFs (for the fallback path + fixtures)

- 2 anonymized invoice PDFs, ideally **two consecutive months for the same
  account**, with **at least one visible delta**;
- if possible one simple and one complex case (expired discount, out-of-bundle
  usage, proration, or an option activated mid-period);
- the matching **`GET /bill-run-documents/search` responses** (`id`, `filename`,
  `contentType`) and the invoice linkage metadata (`accountId`, `invoiceNumber`,
  `billPeriodId`, `billRunId`, `billRunAccountId`, `BillRunAccount` status).

### P2 — Amount semantics (finish OQ-003)

- **Unit:** are amounts in **euros or integer cents**? (`defaultPrice` looks like
  cents, but `AmountResponse` is exposed as a bare `number` — we need certainty to
  map onto our integer-cents convention.)
- **`crud_amount`** (present at every level in the shared model): what does it
  represent — raw/gross, before discount, something else?
- How are **taxes rounded**, and does the invoice total include **previous balance /
  payments** (`balance_previous_bc`, `overdue_amount`) or only current-period lines?

### P2 — Line classifier catalogue (drives business causes)

For `invoice_item` / `ComposedItemResponse`, the full value sets of:

- **`type`**, **`code`**, **`vatType`**;

and how each maps to a V1 **business cause**: discount expiry, usage overage, option
change, proration, tax, one-off fee, adjustment. In particular:

- do **discounts / proration** appear as **negative items**, a dedicated
  `type`/`code`, or a section-level reduction?

### P2 — Enumerating the two invoices to compare

From an `accountId`, the concrete flow to list the **two latest comparable
invoices** (there is no explicit billing-period entity in the shared model). We
believe it is `GET /bill-periods?year=` → `bill-runs` →
`GET /bill-runs/{id}/bill-run-accounts/search?accountIdTerm=` →
`billRunAccountId` / `invoiceNumber` → `invoices/composed` (or PDF). Please confirm
or correct, and tell us which `BillRunAccountResponse.status` values mean an invoice
is usable.

### P3 — Business-cause evidence (per cause)

For each cause (expired discount, mid-period option, proration, out-of-bundle,
offer change, adjustment, one-off fee, tax): the main evidence field, the effective
date, and the **customer-facing wording accepted by billing** (so the KB entries
stay consistent with BSS evidence).

### P3 — Errors and edge cases (for the mock + degraded behaviour)

Standard Galaxion error format; behaviour when the account/invoice/document is not
found, when several documents match, when the BSS is slow/partial; timeouts and
pagination limits.

### P4 — Customer identification (deferred for the pilot, but needed later)

How the customer is identified on the **phone** (Genesys IVR/ANI) and **web voice**
channels, the **minimum confidence** for invoice access, and which data may be
**spoken / displayed / must be masked in logs** (OQ-001). *The pilot ships with a
known/manual identity, so this is a follow-up, not a blocker for Sprint 14.*

## 4. Who provides what

| Item | Owner |
|------|-------|
| `invoices/composed` vs `selected` as structured source + example (P1) | Galaxion billing owner |
| Anonymized PDFs + `bill-run-documents/search` responses + linkage metadata (P1) | Galaxion billing owner |
| Amount unit (euros/cents) + `crud_amount` meaning + tax rounding (P2) | Galaxion billing owner |
| `type` / `code` / `vatType` catalogue + cause mapping (P2) | Galaxion billing owner + our product |
| Two-invoice enumeration flow + usable statuses (P2) | Galaxion billing owner |
| Per-cause evidence + accepted customer wording (P3) | Billing SME + our product |
| Error format + edge cases (P3) | Galaxion billing owner |
| Customer identification rules + masking (P4) | Galaxion / Security + our product |

## 5. What we do without waiting

Per `missing-inputs.md`, we proceed in parallel on fixtures/mock: the billing domain
model (mirroring your `invoice → section → group → item` hierarchy), the
`BssBillingPort` + use cases, the BSS mock with `customer-eir-001…006` fixtures, the
PDF extractor on synthetic PDFs, the deterministic comparison engine, and the QA
journeys. When your answers arrive, the **real `billing-api` read-only adapter** and
**real-data validation** drop in behind the same port without changing the domain.

## 6. Next step

A short working session to walk through **request #1** (structured source vs PDF)
and receive one anonymized composed-invoice example + one PDF pair. That single
answer decides whether PDF extraction is the primary path or a fallback for V1.

## Appendix — Short email cover (ready to send)

> Short version to send as an email body; the full request above is the attachment /
> follow-up. Focused on the two remaining amount questions (unit + `crud_amount`).

**Subject:** Galaxion Billing V1 — 2 quick questions on invoice amounts (+ full input list)

Hi [name],

We're building the V1 billing assistant that explains invoice changes to customers,
using a deterministic comparison of two invoices. Thanks for the billing data model —
it maps cleanly onto our target domain.

**Two quick blockers I'd like to confirm first (invoice amounts):**

1. **Unit** — are the monetary fields (`crud_amount`, `vat_excl_amount`,
   `vat_incl_amount`, `vatIncTotal` / `AmountResponse`) in **euros or integer cents**?
   (`defaultPrice` looks like cents, but `AmountResponse` is exposed as a bare
   `number`, so I'd rather not assume.)
2. **`crud_amount`** — what exactly does this field represent at each level (invoice /
   section / group / item)? Is it the **gross/raw amount before discount**, or
   something else? We need this to know which field drives the comparison.

For context: we've already settled that prices are **tax-included (TTC)**, so our
customer-facing comparison uses the tax-included amount; tax-excluded stays for audit.

**Beyond those two**, I've put together a short, prioritized list of everything we
need from the Galaxion/BSS side to validate V1 on real data — the biggest one being
whether `GET /invoices/composed` can serve as the validated **structured invoice-line
source** (which would let us avoid PDF parsing on the critical path), plus 2 anonymized
invoice PDFs, the `type`/`code`/`vatType` catalogue, and the flow to list the two
invoices to compare. Happy to share that document and walk through it in a 30-min call.

None of this blocks us from starting — we're building on fixtures in the meantime — but
your answers unlock validation against real invoices.

Thanks,
Thomas

## References

- `docs/integrations/galaxion/bss-billing-data-model.md` (the shared real model)
- `docs/integrations/galaxion/galaxion-billing-contracts.md` (`billing-api` routes)
- `docs/integrations/galaxion/bss-integration-plan.md` (access routing)
- `docs/integrations/galaxion/invoice-extraction-json.md` (normalized contract)
- `docs/integrations/galaxion/missing-inputs.md` (source list this consolidates)
- `product-backlog/open-questions/v1-open-questions.md` (OQ-001/003/004)
- `product-backlog/sprints/sprint-14-billing-identity.md` (Sprint 14, TASK-INFRA-017)
