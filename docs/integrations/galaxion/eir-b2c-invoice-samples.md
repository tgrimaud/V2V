# eir B2C invoice samples — model validation

## Purpose

This document records the validation of the V1 billing domain model against **real anonymized eir
B2C invoice PDFs**: three billing accounts, two consecutive bill runs each (August and September
2026). It answers the open questions in `invoice-extraction-json.md`, states the model mapping, and
lists the gaps that ADR-0054 addresses. The transcribed invoices back the realistic mock
(`EirB2cSampleFixtures`, TASK-BE-059).

Source files: the six anonymized test PDFs
(`99224964|99226126|99226337_EIR_MOBILE_TEST_20260812|20260912_B2C.pdf`) are committed as backend test
resources under `backend/src/test/resources/billing/eir-b2c/` (TASK-BE-065). The real eir B2C layout
parser (`EirB2cInvoiceLayoutParser`, `pdf.source=eir-b2c`) parses them, and `EirB2cRealPdfParsingTest`
asserts `parse(real PDF) == EirB2cSampleFixtures` on the full business structure (identity, period
windows, section → group → item tree, inferred category, prorata periods, 23% VAT split, reconciliation).

## Structure observed on the invoice

Each invoice has an "at a glance" header and a "Detail of your eir service" body organized **per
service** (a MSISDN/UAN + product name), each service holding one or two blocks with a subtotal:

- `Subscription and options for the period from X to Y` — recurring charges, billed for the **monthly
  charge period** (forward-looking).
- `One-time charges and adjustments for the period from X to Y` — one-off charges, over the **usage
  period**.

This maps cleanly onto the domain hierarchy:

```
Invoice  →  Section (= service)  →  Group (= block)  →  Item (= line)
```

The header exposes three date notions plus a per-line period:

| Field | Example (September run) | Meaning |
|---|---|---|
| Billing date | `25 Sep 26` | Issue date (**identical across bill runs** in the samples) |
| Usage period | `12 Sep 26 – 11 Oct 26` | Consumption / one-time window = the customer's "this month" |
| Monthly charge period | `12 Oct 26 – 11 Nov 26` | Forward window recurring charges are billed in advance for |
| Line period (proratas) | `eir TV from 25 Sep 26 until 11 Oct 26` | Partial-period charge |

## Per-account deltas (all reconcile exactly on the tax-included basis)

| Account | Services | August (TTC) | September (TTC) | Δ | Main causes M-1 → M |
|---|---|---:|---:|---:|---|
| 99224964 | Mobile | 19.99 | 75.46 | +55.47 | +15GB Bundle (14.99) +15GB prorata (8.50) +eir Mobile Security (1.99) +1GB USA/Canada roaming one-off (29.99) |
| 99226126 | Fibre → Fibre+TV | 139.98 | 73.47 | −66.51 | −FTTH installation one-off (99.99); +new eir TV service (33.48: TV 19.99 + prorata 11.33 − discounts 7.83 + Extra pack 9.99) |
| 99226337 | Fibre+TV → +Mobile | 146.89 | 181.12 | +34.23 | −broadband activation one-off (49.99); TV −1.94 (Aug proratas gone); +new mobile service (86.16) |

Every invoice reconciles with tolerance 0: `Σ line TTC = invoice total TTC`. This validates the
**tax-included comparison basis** on real data even though per-line VAT is absent (see G1).

## Answers to the open questions (`invoice-extraction-json.md`)

| Question | Answer from the samples |
|---|---|
| Do PDFs expose tax-excluded / included / tax **per line**? | **No** — one tax-included amount per line; VAT only at invoice level (single 23% block). |
| Do discounts appear as negative lines or section reductions? | **Negative lines** (e.g. `€46 discount … -46.00`). |
| Do proratas expose an explicit period per line? | **Yes** (`from 25 Sep until 11 Oct`), for both the charge and its matching discount. |
| Do out-of-bundle lines carry volume or only an amount? | Only an amount in these samples (no CDR volume on the PDF). |
| Are invoice sections stable month to month? | **No** — services appear/disappear (installation one month, TV/mobile added the next). Validates ADDED/REMOVED handling in the comparison engine. |
| Is the download always PDF? | These samples are PDF (unverified for other formats). |

## Gaps found and how they are handled

| # | Gap | Handling |
|---|---|---|
| G1 | No per-line VAT (only invoice-level 23%). | Comparison basis is TTC (exact). The mock derives per-line HT/VAT at 23% for audit only; roll-ups reconstitute the TTC total exactly. |
| G2 | `BillingPeriod` had no start/end; `InvoiceItem`/`InvoiceGroup` had no period; the issue date is ambiguous for ordering. | **ADR-0054**: `DateRange` VO; `BillingPeriod(id, invoiceDate, usagePeriod, chargePeriod)` + `orderingDate()`; nullable line/group period; comparator ordered by usage-period start. |
| G3 | No previous-balance / payments / amount-due at invoice level. | Nil on these samples (Outstanding 0, no Payments & Adjustments) → not modeled yet; documented gap for a future carry-forward. |
| G4 | Two period axes (usage vs monthly charge). | Both stored on `BillingPeriod` (`chargePeriod` nullable); `chargePeriod` not yet consumed by the explanation composer (follow-up). |

## Mock data

`EirB2cSampleFixtures.all()` transcribes the six invoices with the real account numbers
(`99224964`, `99226126`, `99226337`), 23% VAT split, section/group/item tree, and prorata line
periods. It is merged with the six synthetic journeys (`BssBillingFixtures`, eir-00X) in the mock
`BssBillingPort` + PDF fallback, and the three accounts are resolvable by number in the mock customer
directory — so the identity → comparable-invoices → comparison → explanation chain runs end-to-end on
realistic data. Recurring and prorated variants of the same product use distinct line codes so they
match line-for-line across months.

## Related documents

- ADR-0054 — billing period model for real eir B2C invoices
- `invoice-extraction-json.md` — target extraction contract
- `bss-billing-data-model.md` — BSS hierarchy
- ADR-0005 (PDF extraction before LLM), ADR-0052 (billing explanation behind the answer engine)
