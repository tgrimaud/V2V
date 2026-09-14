# Eir Billing Services — Real Contract (Billing V1)

> Source of truth for the **real** billing adapter (TASK-BE-047). Captured 2026-09-14 from the
> dev OpenAPI specs shared by the user. Versioned copies:
> `assets/openapi-billing-enquiry-service-3.1.0.json`, `assets/openapi-billing-service-2.3.1.json`.
> This supersedes the earlier `billing-api` / `invoices/composed` assumption (see "Corrections").

## Objective

Document the two Eir services the `BssBillingPort` will call, map their contract onto our
billing domain (`Invoice → section → group → item`, tax-included comparison basis), and record
what these specs answer / still leave open for real-data validation (OQ-003/004, QA-020).

## Source Systems

| Service | Version | Base URL (dev) | Role |
|---|---|---|---|
| `billing-enquiry-service` | 3.1.0-SNAPSHOT | `https://billing-enquiry-service.eir-dev.itsf.io` | Structured **amount breakdown** + bill history (read) |
| `billing-service` | 2.3.1 | `https://billing-service.eir-dev.itsf.io` | Invoice history list, **PDF** + **CSV** reports, resend (read + one write we don't use) |

Both are read-only for our purposes (we never call `resend`). Neither declares an OpenAPI
security scheme; **authorization is carried by two required headers on every call**:

- `galaxion-user-type`: enum `REGISTERED | PRIVILEGED | SYSTEM`
- `galaxion-user-identifier`: string

These headers are the BSS authorization context and must be derived from the resolved identity
(BR-002-1), never hardcoded to `SYSTEM` in the customer path.

## Endpoints We Use

### billing-enquiry-service (structured, preferred for comparison)

- `GET /bill_enquiry?billingAccountId={int}[&invoiceId={int}]` → `BillEnquiryResponseDTO`
  — bill **history** for an account: `bills[]` of `BillDetailResponseDTO`.
- `GET /billing-enquiry/invoices/{invoiceId}` → `InvoiceResponseDTO` — one invoice with its
  **amount breakdown**.

### billing-service (list + document reports)

- `GET /api/v1/accounts/{account_id}/invoices` → `InvoiceHistoryResponse[]` — invoice list.
- `GET /api/v1/invoices/{invoice_number}/details` → `InvoiceDetailsResponse` — **thin in the
  spec** (only `accountId`, `invoiceNumber`); real line-level shape must be confirmed on a sample.
- `GET /api/v1/invoices/{invoice_number}?accountId={string}[&optionalInvoice]` → `application/pdf`.
- `GET /api/v1/invoices/{invoice_number}/detail-report` → `text/csv` — **line detail (CSV)**.
- `GET /api/v1/invoices/{invoice_number}/summary-report` → `text/csv` — summary (CSV).

## Data Contract (as specified)

`BillAmountResponseDTO` (enquiry) — all `integer int64`:

| Field | Meaning (to confirm) |
|---|---|
| `invoiceAmount` | invoice total |
| `recurringAmount` | recurring / subscription part |
| `oneOffAmount` | one-off charges |
| `usageAmount` | out-of-bundle usage |
| `vatAmount` | tax |

`InvoiceResponseDTO`: `accountId(int64)`, `invoiceId(int64)`, `billPeriod(string)`,
`billAmount(BillAmountResponseDTO)`, `effectiveDate(date-time)`.
`BillDetailResponseDTO`: `invoiceId`, `billPeriod`, `effectiveDate`, `billAmount`.
`InvoiceHistoryResponse` (billing-service): `amount(int64)`, `invoiceNumber(int64)`,
`invoiceDate(date)`, `dueDate(date)`.

## Mapping To `BssBillingPort`

| Port method | Primary call | Notes |
|---|---|---|
| `listInvoices(AccountId)` → `List<InvoiceSummary>` | `GET /bill_enquiry?billingAccountId=` (enquiry) or `GET /api/v1/accounts/{id}/invoices` (billing-service) | Enquiry returns amount breakdowns per period; billing-service returns a lean list. Pick the two most recent comparable invoices. |
| `fetchInvoice(AccountId, InvoiceId)` → `Invoice` | `GET /billing-enquiry/invoices/{invoiceId}` (enquiry) | Gives a **category-level** breakdown (recurring/oneOff/usage/vat/total), not the full `section → group → item` tree. |
| line-level detail (fallback) | `GET /api/v1/invoices/{n}/detail-report` (**CSV**) or the PDF | CSV is a far more deterministic extraction target than the PDF; the PDF stays the last-resort fallback. |

### Cause attribution from the breakdown

The enquiry breakdown maps coarsely onto `BillingCauseType`: `usageAmount` → `USAGE_OVERAGE`,
`oneOffAmount` → `ONE_OFF_FEE`, `vatAmount` → `TAX`, `recurringAmount` → subscription/discount/
option/proration bucket (needs finer lines to separate `DISCOUNT_EXPIRY` / `OPTION_CHANGE` /
`PRORATION`). Finer attribution requires the CSV `detail-report` or the PDF.

## Independent-Adapter Design (BE-047)

Per the directive to keep port implementations as decoupled as possible:

1. **One domain seam:** the domain and answer engine keep depending only on `BssBillingPort`
   (+ `InvoicePdfExtractorPort`). No Eir DTO ever crosses the adapter boundary.
2. **One thin HTTP client per service** (`BillingEnquiryClient`, `BillingServiceClient`), each
   with its own base URL, timeouts and the two `galaxion-user-*` headers. A service can change,
   move or be swapped without touching the other or the domain.
3. **A single `EirBssBillingAdapter`** composes those clients behind `BssBillingPort` and maps
   external DTOs → domain (`Invoice`, `InvoiceSummary`, `LineAmounts`, `BillingPeriod`).
4. **Config-driven selection** (`voice-support.billing.bss.source`: `mock` → `eir`), so the
   in-memory adapter stays the default until real data validates the path; per-service base URLs
   and header policy are properties, not code constants.
5. **Extraction independence:** structured enquiry first; if line-level detail is needed, prefer
   the **CSV** `detail-report` extractor over PDF; the PDF extractor stays a separate adapter
   behind `InvoicePdfExtractorPort`.
6. **Fail-closed & scoped:** every call scoped by `AccountId`; a non-privileged
   `galaxion-user-type` or a not-found/ambiguous result escalates rather than guesses (BR-002-1).

## What These Specs Answer

- **Amount unit:** amounts are **integers** (`int64`) — aligns with our integer-minor-units
  convention (still confirm cents vs pennies on a sample). Largely closes the OQ-003 unit question.
- **Structured source exists:** the enquiry `BillAmountResponseDTO` gives a category-level
  breakdown without parsing a PDF — so **PDF parsing is a fallback, not the primary path** for
  the coarse comparison.
- **A CSV line-detail report exists** (`detail-report`) — a deterministic extraction target that
  is much safer than PDF for line-level causes.
- **Auth model:** two `galaxion-user-*` headers (type enum + identifier), no token scheme in the spec.

## Missing Inputs / Open Questions

- Real shape of `InvoiceDetailsResponse` and of the **CSV** `detail-report` (columns) on a sample
  — the OpenAPI under-describes the details endpoint.
- Is `int64` in **cents** (or pennies)? Confirm on one anonymized example.
- Does `invoiceAmount` include previous balance / payments, or only current-period lines?
- Line-level catalogue to separate `DISCOUNT_EXPIRY` / `OPTION_CHANGE` / `PRORATION` inside
  `recurringAmount` (needs the CSV/PDF lines + a code/type catalogue).
- Account id typing mismatch: enquiry uses `billingAccountId` **int64**, billing-service uses
  `account_id` **string** — confirm the canonical account identifier and the invoice-id linkage
  (`invoiceId` vs `invoiceNumber`).
- Error format + behaviour for not-found / multiple matches / slow BSS (for degraded modes).

## Corrections To Earlier Assumptions

- The real sources are **`billing-enquiry-service`** and **`billing-service`** (Eir dev), not the
  hypothetical `billing-api` with `GET /invoices/composed`. The prior "use `billing-api`, not
  `billing-service`" note (CLAUDE.md) does **not** match this environment — `billing-service`
  (v2.3.1) is one of the two services we integrate with. Treat this document as authoritative for
  BE-047; `galaxion-billing-contracts.md` describes the earlier assumption and should be read as
  historical until reconciled.

## Next Steps

1. Confirm the open items above on **one anonymized sample** per endpoint (feeds QA-020 fixtures).
2. Implement BE-047 with the independent-adapter design above (behind `BssBillingPort`), default
   `source=mock` until validated.
3. Prefer the CSV `detail-report` extractor over PDF for line-level causes.
