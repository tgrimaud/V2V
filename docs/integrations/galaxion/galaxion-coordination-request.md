# Galaxion / BSS — Coordination Request (Billing V1)

> Ticket: TASK-INFRA-017 (finalized) · follow-up **TASK-INFRA-018** (B2C granularity pivot) · Sprint 14 · Status: **request finalized — ready to send** (refreshed 2026-09-16: Galaxion confirmed line-level detail is B2B-only → the ask pivots to raw-PDF availability for B2C)
> Audience: Galaxion / BSS billing owners + our backend/product team.

## 1. Purpose

We are building the V1 billing assistant: it explains to a customer **why an
invoice changed** by comparing two invoices with a **deterministic engine**
(amounts and causes computed by code; the LLM only phrases the confirmed, traceable
result — it never computes amounts). This document centralizes what we still need
from the Galaxion / BSS side to validate V1 against **real** data.

Since the previous version, we have **integrated the real Eir dev services**
(`billing-enquiry-service` 3.1.0 + `billing-service` 2.3.1) behind our read-only
`BssBillingPort` and **validated the structured path live on test account 5**
(`docs/integrations/galaxion/eir-billing-services-contract.md` § Live validation).
That closed several earlier questions (see §2) and narrowed the remaining blockers
to **two concrete items** (see §3, P1). The build does **not** wait on these — we run
on fixtures + a BSS mock and `source=mock` by default — but **real-data acceptance
(QA-020) and enabling `source=eir`** do.

## 2. What is already decided or validated on our side (please do not re-answer)

Settled by us:

- **Real sources = `billing-enquiry-service` (invoice breakdown) + `billing-service`
  (account invoice list)**, Eir dev. This supersedes the earlier `billing-api` /
  `invoices/composed` framing.
- **Prices are tax-included (TTC)** (confirmed 2026-09-09) → the customer-facing
  comparison basis is the tax-included amount; tax-excluded stays for audit only.
- **Access is read-only** through a typed port (`BssBillingPort`, ADR-0004); we never
  mutate BSS data in V1.

Confirmed live on **test account 5** (2026-09-15) — no need to re-answer:

- **Unit = integer cents.** `amount 3999` = €39.99; `vatAmount 748` = 23% Irish VAT
  contained inside the total (closes the OQ-003 unit question).
- **VAT is inside `invoiceAmount`, not additive:** `invoiceAmount 3999 ==
  recurringAmount 3999`, `vatAmount 748` is the contained tax. Our mapping reconciles
  category (TTC) lines to `invoiceAmount` and keeps the VAT split at invoice level only.
- **Identifier linkage:** enquiry `billingAccountId` (int64) and billing-service
  `account_id` (string) are the **same identifier space**; `invoiceId` ==
  `invoiceNumber`. We enforce BR-002-1 ownership (numeric owner compare, fail-closed)
  on `fetchInvoice`.
- **Auth model:** two headers `galaxion-user-type` (enum `PRIVILEGED|SYSTEM`) +
  `galaxion-user-identifier`; no token scheme in the spec.
- **Error format:** RFC 7807 `application/problem+json` (`errorCode`, `title`,
  `status`, `detail`, `sources`) — wired into our degraded-mode handling.

## 3. Requests (prioritized)

### P1 — B2C line-level granularity: is the raw invoice PDF available for residential? (top blocker)

**New finding (2026-09-16):** Galaxion confirmed the line-level `billing-service`
endpoints (`/api/v1/invoices/{invoice_number}/{details,detail-report,summary-report}`)
return data **only for B2B accounts**. Our test account 5 is B2C/residential, which is
why `details` is empty and `detail-report`/`summary-report` return HTTP 412
`archive-file-token-is-null`. **V1 targets B2C end users**, so for the actual audience
the archived line detail (and its archive token) **does not apply** — chasing the token
is moot for V1.

For B2C, the only remaining line-level lever is the **raw invoice PDF**
`GET /api/v1/invoices/{invoice_number}` (`getInvoice`) — distinct from the B2B archive
reports (its `galaxion-user-type` enum even allows `REGISTERED`).

**Pivotal question:** is `getInvoice` (raw PDF) served for a **B2C/residential**
account?

- **If yes** → we extract the PDF into structured JSON deterministically before any
  comparison (ADR-0005; the LLM never reads the PDF), which stays the V1 line-level path.
  We would then need 2 anonymized B2C PDFs (two periods, one visible delta).
- **If no** → confirm there is **no** line-level source for B2C; V1 then explains at the
  coarse-bucket level (recurring/usage/one-off/vat) and escalates any change it cannot
  attribute — an explicit, accepted V1 limitation.

### P2 (was P1) — Archive token / B2B detail (only if B2B ever enters scope)

If a B2B path is ever in V1 scope: how is the archive token/flow obtained for
`detail-report` / `summary-report`, and the CSV column shape. **Out of the V1 critical
path** given the B2C-only decision.

### P2 — A B2C account (or period) with two comparable invoices

Account 5 has a **single** invoice, so there is **no real delta to compare** yet — our
comparison engine and QA-020 need two invoices for the same account.

**Request:** a dev account with **at least two consecutive invoices** (or a second
billing period on account 5) exhibiting a **visible delta**; ideally one simple case
(expired discount / out-of-bundle usage) and one complex case (proration / mid-period
option change).

### P2 — `invoiceAmount` composition

Does `invoiceAmount` cover **only the current-period charges**, or does it also include
**previous balance / payments / overdue**? This decides whether we compare period totals
directly or must isolate current-period charges before diffing.

### P2 — Line classifier catalogue (drives business causes)

Once the archive token unlocks the CSV/PDF lines, we need the value sets and mapping for
the line fields (`type` / `code` / `vatType` or the CSV column equivalents) onto the V1
business causes: **discount expiry, usage overage, option change, proration, tax,
one-off fee, adjustment**. In particular: do **discounts / proration** appear as negative
lines, a dedicated `type`/`code`, or a section-level reduction?

### P2 — CSV `detail-report` column shape

The exact columns of the CSV `detail-report` (blocked today by the P1 token) so we can
map them onto our structured invoice model deterministically.

### P3 — Errors and edge cases (for the mock + degraded behaviour)

Beyond the RFC 7807 format we already see: behaviour when the account/invoice is not
found, when several documents match, when the service is slow/partial; timeouts and
pagination limits on the invoice list.

### P3 — Business-cause evidence (per cause)

For each cause (expired discount, mid-period option, proration, out-of-bundle, offer
change, adjustment, one-off fee, tax): the main evidence field, the effective date, and
the **customer-facing wording accepted by billing**, so the KB entries stay consistent
with BSS evidence.

### P4 — Customer identification + `galaxion-user-*` derivation (deferred for the pilot)

How the customer is identified on the **phone** (Genesys IVR/ANI) and **web voice**
channels, the **minimum confidence** for invoice access, what may be
**spoken / displayed / must be masked in logs** (OQ-001), and **how the two
`galaxion-user-*` header values are derived** per real caller (the pilot currently uses a
configured default). *Follow-up, not a Sprint 14 blocker.*

## 4. Who provides what

| Item | Priority | Owner |
|------|----------|-------|
| **Is `getInvoice` (raw PDF) available for a B2C account?** (else confirm no B2C line source) | P1 | Galaxion billing owner |
| B2C dev account with ≥2 comparable invoices (or a 2nd period) | P2 | Galaxion billing owner |
| `invoiceAmount` composition (current-period vs balance/payments) | P2 | Galaxion billing owner |
| Archive-token flow + CSV columns (only if B2B ever in scope) | P2 | Galaxion billing owner |
| Line catalogue (`type`/`code`/`vatType`) + cause mapping (if a line source exists for B2C) | P2 | Galaxion billing owner + our product |
| Error/edge-case behaviour + pagination limits | P3 | Galaxion billing owner |
| Per-cause evidence + accepted customer wording | P3 | Billing SME + our product |
| Customer identification rules + `galaxion-user-*` derivation + masking | P4 | Galaxion / Security + our product |

## 5. What we do without waiting

We proceed on fixtures/mock (`source=mock` default): the billing domain model, the
`BssBillingPort` + use cases, the BSS mock with `customer-eir-001…006` fixtures, the PDF
extractor on synthetic PDFs, the deterministic comparison engine, and the QA journeys.
The **real Eir adapter is already implemented** behind the port and validated on the
coarse structured path; enabling `source=eir` for line-level attribution and running
QA-020 is what the P1 items above unlock.

## 6. Next step

A short working session on the **pivotal B2C question**: does `getInvoice` return the raw
PDF for a residential account? That single answer decides whether V1 can attribute
fine-grained causes (via deterministic PDF extraction, ADR-0005) or explains at the
coarse-bucket level and escalates the rest — and, with a B2C 2-invoice account, unblocks
real-data acceptance (QA-020, TASK-INFRA-018).

## Appendix — Short email cover (ready to send)

> Focused on the two concrete P1 blockers surfaced by the live test on account 5.

**Subject:** Eir Billing V1 (B2C) — line-level detail for residential accounts + a 2-invoice test account

Hi [name],

Thanks — we've integrated the Eir dev billing services (`billing-enquiry-service` +
`billing-service`) behind our read-only port and validated the structured path live on
**test account 5**. Essentials confirmed: amounts are in **cents**, **VAT is contained
in the invoice total** (not additive), and `invoiceId` == `invoiceNumber` with a single
shared account identifier.

Thanks also for confirming the **line-level endpoints** (`…/details`,
`…/detail-report`, `…/summary-report`) are **B2B-only** — that explains the empty
`details` / HTTP 412 on account 5 (which is B2C). Since **our V1 targets B2C /
residential end users**, that reframes what we need:

1. **Is the raw invoice PDF available for a B2C account?** i.e. does
   `GET /api/v1/invoices/{invoice_number}` (`getInvoice`) return the PDF for a
   residential account? If yes, we extract it into structured data deterministically
   before any explanation (we never let the model read the PDF). If **no** line-level
   source exists for B2C, please confirm — we'll then explain at the coarse level
   (subscription / usage / one-off / VAT) and hand off anything we can't attribute.
2. **A B2C test account with two invoices** — account 5 has a single invoice, so there's
   **no delta to compare**. Could we get a residential dev account with at least two
   consecutive invoices (or a second period) showing a visible change?

Secondary, when convenient: does `invoiceAmount` include previous balance/payments or
only current-period charges.

None of this blocks our build — we run on fixtures in the meantime — but these unlock
validation against real B2C invoices. Happy to walk through it in a 30-min call.

Thanks,
Thomas

## References

- `docs/integrations/galaxion/eir-billing-services-contract.md` (real Eir services + live validation on account 5)
- `docs/integrations/galaxion/bss-billing-data-model.md` (shared real model)
- `docs/integrations/galaxion/bss-integration-plan.md` (access routing)
- `docs/integrations/galaxion/invoice-extraction-json.md` (normalized contract)
- `docs/integrations/galaxion/missing-inputs.md` (source list this consolidates)
- `product-backlog/open-questions/v1-open-questions.md` (OQ-001/003/004)
- `product-backlog/sprints/sprint-14-billing-identity.md` (Sprint 14, TASK-INFRA-017)
