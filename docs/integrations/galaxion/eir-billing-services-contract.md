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

## Live validation — test account 5 (2026-09-15)

First real calls against the Eir dev services (VPN), `galaxion-user-type: SYSTEM` (enum is
`PRIVILEGED|SYSTEM`), `galaxion-user-identifier: SYSTEM`:

- `GET /api/v1/accounts/5/invoices` → `200` `[{"amount":3999,"invoiceNumber":2608020000000067,"invoiceDate":"2026-07-08","dueDate":"2026-07-22"}]`.
- `GET /billing-enquiry/invoices/2608020000000067` → `200` `{"accountId":5,"invoiceId":2608020000000067,"billPeriod":"202608","billAmount":{"vatAmount":748,"recurringAmount":3999,"oneOffAmount":0,"usageAmount":0,"invoiceAmount":3999},"effectiveDate":"2026-09-01T00:00:00"}`.
- `GET /bill_enquiry?billingAccountId=5` → `200` same bill nested under `bills[]` (richer list, breakdown per period).

**Confirmed:**
- **Unit = cents.** `3999` = €39.99; `vatAmount 748` = 23% Irish VAT (3999/1.23 ≈ 3251 + 748).
- **`invoiceId` == `invoiceNumber`** (`2608020000000067` addresses both services) — linkage resolved.
- **`accountId` = 5** (int) on the enquiry response → BR-002-1 numeric ownership guard validates.
- **VAT is contained in the total, not additive:** `invoiceAmount 3999 == recurringAmount 3999`,
  `vatAmount 748` is inside it → the adapter no longer emits a separate TAX line (bug fixed this session).
- **Date/period:** `effectiveDate` `2026-09-01T00:00:00` (no `Z`), `billPeriod` `202608` (yyyyMM) —
  `parseDate` (first 10 chars) handles both.

**Line-level detail is B2B-only (Galaxion, 2026-09-16) — material for V1 (B2C):**
- The line-level endpoints live on **`billing-service`** (not `billing-enquiry-service`):
  `GET /api/v1/invoices/{invoice_number}/details`, `…/detail-report` (CSV), `…/summary-report`.
- Galaxion confirmed these return data **only for a B2B account**. Test account 5 is **B2C/residential**,
  so `details` → `200` but **empty** and `detail-report`/`summary-report` → **HTTP 412**
  `archive-file-token-is-null`. The archive token is therefore **not merely "to be generated"** — for a
  B2C account it does not exist, so the token is **largely moot for V1** (V1 = B2C-only, 2026-09-16).
- Consequence for V1: for the target audience we are limited to the **coarse** `billing-enquiry`
  breakdown → intra-`recurringAmount` deltas stay `UNEXPLAINED` and escalate (fail-closed), **unless**
  the raw PDF path below is available for B2C.
- **Pivotal open question:** is the **raw invoice PDF** `GET /api/v1/invoices/{invoice_number}`
  (`getInvoice`, distinct from the B2B archive reports; its `galaxion-user-type` enum also allows
  `REGISTERED`) served for a **B2C** account? If yes → ADR-0005 PDF→JSON extraction stays the V1
  line-level path; if no → V1 for B2C is coarse-bucket + escalate (explicit limitation). Tracked as
  **TASK-INFRA-018**.
- Error format is **RFC7807** `application/problem+json` (`errorCode`, `title`, `status`, `detail`,
  `sources`) — use for degraded-mode handling.
- Account 5 has a **single invoice** → no two-invoice comparison possible; need another account or a
  second period for a real delta (QA-020).

## Missing Inputs / Open Questions

- ~~Is `int64` in cents?~~ **Resolved: cents** (account 5). Confirm currency field is absent → EUR default holds.
- ~~How is the **archive token** obtained?~~ **Superseded (2026-09-16):** the line-level detail is
  **B2B-only**; for the B2C V1 target the token does not apply. See the B2B-only finding above.
- **Pivotal:** is the raw PDF `GET /api/v1/invoices/{invoice_number}` (`getInvoice`) available for a
  **B2C** account (→ ADR-0005 extraction stays viable), or is V1 coarse-only for B2C? (TASK-INFRA-018)
- Real shape of the **CSV** `detail-report` columns — only relevant if a B2B path is ever in scope.
- Does `invoiceAmount` include previous balance / payments, or only current-period lines?
- Line-level catalogue to separate `DISCOUNT_EXPIRY` / `OPTION_CHANGE` / `PRORATION` inside
  `recurringAmount` (needs the CSV/PDF lines + a code/type catalogue).
- ~~Account id typing mismatch~~ **Resolved 2026-09-15:** enquiry `billingAccountId` (int64) and
  billing-service `account_id` (string) are the **same identifier** (one space); `invoiceId` == `invoiceNumber`.
  The Eir adapter enforces BR-002-1 defense-in-depth on `fetchInvoice` (numeric owner compare, fail-closed).

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
