# Galaxion Billing - Initial V1 Contract

## Analyzed Sources

Analyzed Swagger contracts:

| Service | URL OpenAPI | Version | Paths | Schemas |
|---------|-------------|---------|-------|---------|
| `billing-api` | `https://billing-api.rke-itsf-devgalaxioncore-prd.itsf.io/v3/api-docs` | `1.4.0-SNAPSHOT` | 26 | 34 |
| `billing-service` | `https://billing-service.rke-itsf-devgalaxioncore-prd.itsf.io/v3/api-docs` | `2.5.0-SNAPSHOT` | 7 | 5 |

## Quick Read

Updated decision: `billing-service` is no longer used. The V1 target must use
only `billing-api` for the Billing scope.

`billing-service` remains documented below only as a historical reference for
the analysis. It must not be implemented in the V1 mock, nor used by the Voice
Support Bot backend.

`billing-api` exposes bill run, billing period and invoice endpoints. For Voice
Support Bot V1, the directly useful endpoints are:

- `/bill-periods`
- `/bill-periods/{bill_period_id}`
- `/bill-runs/{bill_run_id}/bill-run-accounts/search`
- `/bill-run-documents/search`
- `/bill-run-documents/{document_id}/download`

Target flow: bill periods -> bill runs -> bill run accounts -> invoice
documents -> invoice PDF -> structured extraction.

## Integration Decision

| Topic | Decision |
|-------|----------|
| Target Billing source | `billing-api` only |
| `billing-service` | Not used / outside V1 target |
| Invoice/document search | `GET /bill-run-documents/search` |
| Invoice/document download | `GET /bill-run-documents/{document_id}/download` |
| Usable invoice detail | Structured extraction from the invoice PDF |
| Period selection | `GET /bill-periods?year={year}` |
| Account -> invoice link | `GET /bill-runs/{bill_run_id}/bill-run-accounts/search` |
| V1 mock | Reproduce useful `billing-api` endpoints, not `billing-service` endpoints |

## Billing-Service Not Retained

`billing-service` exposes endpoints that are closer to the customer journey, but
it is no longer used in Galaxion for this need. This section remains archived to
explain why it must not be taken as a V1 dependency.

### Invoice History By Account Not Retained

```text
GET /api/v1/accounts/{account_id}/invoices
```

Parameters:

| Name | In | Required | Type | V1 Usage |
|-----|----|-------------|------|----------|
| `account_id` | path | yes | string | Customer account |
| `galaxion-user-type` | header | yes | string | Galaxion user context |
| `galaxion-user-identifier` | header | yes | string | Galaxion user identifier |

Documented responses:

| Code | Description | Schema |
|------|-------------|--------|
| 200 | Success | `InvoiceHistoryResponse[]` |
| 401 | Unauthorized, problem title `access-not-authorized` | `InvoiceHistoryResponse[]` in the Swagger |
| 404 | Account not found, problem title `account-not-found` | `InvoiceHistoryResponse[]` in the Swagger |

Useful fields from `InvoiceHistoryResponse`:

| Field | Type | V1 Usage |
|-------|------|----------|
| `invoiceNumber` | int64 | Main key to retrieve the invoice |
| `amount` | int64 | Invoice amount, unit to confirm |
| `invoiceDate` | date | Invoice date |
| `dueDate` | date | Due date |

Reading:

This endpoint seemed to directly address the need to "list invoices/periods" for
an account, but it must not be used in the V1 target because `billing-service`
is out of use.

### Retrieve Invoice PDF Not Retained

```text
GET /api/v1/invoices/{invoice_number}?accountId={accountId}&optionalInvoice={optionalInvoice}
```

Useful parameters:

| Name | In | Required | Type | V1 Usage |
|-----|----|-------------|------|----------|
| `invoice_number` | path | yes | int64 | Invoice number |
| `accountId` | query | yes | string | Customer account |
| `optionalInvoice` | query | no | boolean | Invoice option |
| `galaxion-user-type` | header | yes | string | Galaxion user context |
| `galaxion-user-identifier` | header | yes | string | Galaxion user identifier |

Response:

```text
200 -> application/pdf
```

V1 reading:

The PDF is not the best support for the deterministic engine, but it can serve
as evidence or a human fallback. It must not become the main calculation source
if structured data exists.

### Retrieve Invoice Details Not Retained

```text
GET /api/v1/invoices/{invoice_number}/details
```

Parameters:

| Name | In | Required | Type |
|-----|----|-------------|------|
| `invoice_number` | path | yes | int64 |
| `galaxion-user-type` | header | yes | string |
| `galaxion-user-identifier` | header | yes | string |

Response:

```text
200 -> InvoiceDetailsResponse
```

Documented schema:

| Field | Type | V1 Usage |
|-------|------|----------|
| `accountId` | string | Customer account |
| `invoiceNumber` | int64 | Invoice number |

V1 reading:

The Swagger documents only `accountId` and `invoiceNumber`. This may mean that
the schema is incomplete in the documentation, or that the real detail is carried
by the CSV/PDF outputs or by `billing-api`. Before concluding, a real response
example must be tested or an anonymized payload requested.

### Invoice CSV Reports Not Retained

```text
GET /api/v1/invoices/{invoice_number}/detail-report
GET /api/v1/invoices/{invoice_number}/summary-report
```

Response:

```text
200 -> text/csv
```

V1 reading:

These endpoints must not be reproduced in the V1 mock as long as
`billing-service` remains outside the target.

## Billing-api

### Endpoints Retained For The V1 Mock

### Retrieve Billing Periods

```text
GET /bill-periods?year={year}
```

Parameters:

| Name | In | Required | Type | Notes |
|-----|----|-------------|------|-------|
| `year` | query | yes | integer | Period year |

Response:

```text
200 -> BillPeriodResponse[]
```

Useful fields:

| Field | V1 Usage |
|-------|----------|
| `id` | Galaxion period identifier |
| `year` | Billing year |
| `month` | Billing month |
| `billRuns[]` | Bill runs associated with the period |

### Retrieve A Billing Period

```text
GET /bill-periods/{bill_period_id}
```

Parameters:

| Name | In | Required | Type |
|-----|----|-------------|------|
| `bill_period_id` | path | yes | uuid |

Response:

```text
200 -> BillPeriodResponse
```

### Search Accounts In A Bill Run

```text
GET /bill-runs/{bill_run_id}/bill-run-accounts/search
```

Useful V1 parameters:

| Name | In | Required | Type | V1 Usage |
|-----|----|-------------|------|----------|
| `bill_run_id` | path | yes | uuid | Bill run from the period |
| `accountIdTerm` | query | no | string | Filter by customer account |
| `billPeriodId` | query | no | uuid | Restrict to the period |
| `page` | query | no | integer | Pagination |
| `size` | query | no | integer | Pagination |
| `statuses` | query | no | array | Filter statuses if needed |

Response:

```text
200 -> PagedResponseBillRunAccountResponse
```

Useful fields from `BillRunAccountResponse`:

| Field | V1 Usage |
|-------|----------|
| `id` | `billRunAccountId`, needed to retrieve an invoice |
| `accountId` | Billed account |
| `invoiceNumber` | Invoice number, another possible key |
| `status` | Check whether the invoice is usable |
| `currentStep` | Diagnostic if the invoice is incomplete |
| `errorType` / `errorMessage` | Error case to expose or escalate |
| `brand` | Brand |
| `accountType` | B2C/B2B or equivalent |

### Search Invoice Documents

```text
GET /bill-run-documents/search
```

Useful V1 parameters:

| Name | In | Required | Type | V1 Usage |
|-----|----|-------------|------|----------|
| `billRunAccountId` | query | no | uuid | Direct search from the bill run account |
| `accountId` | query | no | string | Search by customer account |
| `invoiceNumber` | query | no | string | Search by invoice number |
| `billPeriodId` | query | no | uuid | Search by period |

Response:

```text
200 -> BillRunDocumentResponse[]
```

Useful fields from `BillRunDocumentResponse`:

| Field | Type | V1 Usage |
|-------|------|----------|
| `id` | uuid | Identifier of the document to download |
| `filename` | string | Invoice document name |
| `contentType` | string | Document content type |

V1 reading:

This endpoint is the entry point for retrieving an invoice/document from one or
more criteria: `billRunAccountId`, `accountId`, `invoiceNumber`,
`billPeriodId`. It must be reproduced in the mock because it covers the
"find the invoice" case without imposing a single call identifier.

### Download An Invoice Document

```text
GET /bill-run-documents/{document_id}/download
```

Parameters:

| Name | In | Required | Type | V1 Usage |
|-----|----|-------------|------|----------|
| `document_id` | path | yes | uuid | Document returned by `/bill-run-documents/search` |
| `billPeriodId` | query | no | uuid | Period context if needed |

Response:

```text
200 -> application/octet-stream
```

V1 reading:

The downloaded document is the main source for invoice detail when Galaxion does
not provide a structured endpoint for invoice lines. The backend must extract
the useful data from the PDF into an internal structured format before running
the comparison engine.

### Retrieve A Selected Invoice

```text
GET /invoices/selected
```

Parameters:

| Name | In | Required | Type | Notes |
|-----|----|-------------|------|-------|
| `billRunAccountId` | query | no | uuid | Most direct key if known |
| `invoiceNumber` | query | no | string | Alternative |
| `billPeriodId` | query | no | uuid | Period filter |

Response:

```text
200 -> SelectedInvoiceResponse
```

V1 reading:

`selected` seems to represent the selected/calculable invoice, with lines and
sections, but without explicit composed amounts at invoice, section and item
level. Items carry `defaultPrice` in cents, taxes and reference/effective
periods.

### Composed Invoice Not Retained For V1 Invoice Detail

```text
GET /invoices/composed
```

Parameters:

| Name | In | Required | Type | Notes |
|-----|----|-------------|------|-------|
| `billRunAccountId` | query | no | uuid | Most direct key if known |
| `invoiceNumber` | query | no | string | Alternative |
| `billPeriodId` | query | no | uuid | Period filter |

Response:

```text
200 -> ComposedInvoiceResponse
```

Reading:

`invoices/composed` does not match the current need to retrieve customer invoice
detail. It must not be used as the main source for the V1 mock until its exact
role in Galaxion is clarified.

## Invoice PDF Extraction

Because no structured invoice-line endpoint has been identified, V1 must
introduce an `InvoicePdfExtractor` component.

```text
Galaxion invoice PDF
        |
        v
InvoicePdfExtractor
        |
        v
Normalized invoice JSON
        |
        v
Deterministic comparison engine
```

Responsibilities:

- extract text and tables from the invoice PDF;
- identify the invoice total, dates, sections and lines;
- normalize amounts, currencies, taxes, discounts, fees and prorations;
- produce a stable internal JSON for the comparison engine;
- report unparsed or ambiguous areas;
- verify that extracted lines reconcile with the total within a defined
  tolerance.

The LLM must not read the PDF directly to infer amounts. It can formulate the
explanation only after structured extraction and validation.

### Target Extraction JSON

The exact format will be adjusted after reviewing anonymized PDFs. The working
version is detailed in
[`invoice-extraction-json.md`](invoice-extraction-json.md).

The structuring principles are:

- amounts as integer cents (`*_cents`);
- extraction status: `parseable`, `partial` or `unusable`;
- textual evidence attached to extracted lines;
- normalized warnings for ambiguous areas;
- explicit reconciliation between line sum and invoice total.

Simplified excerpt:

```json
{
  "schema_version": "invoice-extraction.v1",
  "extraction": {
    "status": "parseable",
    "confidence": "high",
    "warnings": []
  },
  "source_document": {
    "source": "billing-api",
    "document_id": "2f6098b1-83e4-4cc0-8a2a-4e7d3f70d5f5",
    "filename": "invoice-2026-06-100231079.pdf"
  },
  "invoice": {
    "invoice_number": "202606100231079",
    "account_id": "100231079",
    "period": {
      "start": "2026-06-01",
      "end": "2026-06-30"
    },
    "currency": "EUR",
    "amounts": {
      "total_tax_included_cents": 6840
    }
  },
  "sections": [
    {
      "id": "section-subscriptions",
      "label": "Monthly charges",
      "category": "subscription",
      "lines": [
        {
          "id": "line-001",
          "label": "Mobile plan 100GB",
          "category": "subscription",
          "amount_tax_included_cents": 2999,
          "evidence": {
            "page": 2,
            "text": "Mobile plan 100GB 01 Jun - 30 Jun EUR 29.99"
          },
          "extraction_confidence": "high",
          "warnings": []
        }
      ]
    }
  ],
  "reconciliation": {
    "status": "reconciled",
    "line_sum_tax_included_cents": 6840,
    "invoice_total_tax_included_cents": 6840,
    "difference_cents": 0,
    "tolerance_cents": 1,
    "unexplained_amount_cents": 0
  }
}
```

## Useful Schemas Outside The Main Path

### `ComposedInvoiceResponse`

Fields that may be useful if `invoices/composed` is requalified later:

| Field | Type | Usage |
|-------|------|-------|
| `id` | uuid | Invoice identifier |
| `billRunAccountId` | uuid | Invoice key in the bill run |
| `billRunId` | uuid | Source bill run |
| `accountId` | string | Billed account |
| `invoiceNumber` | string | Invoice number |
| `dueDate` | date | Due date |
| `usagePeriod` | `BillingPeriodResponse` | Usage period |
| `recurringPeriod` | `BillingPeriodResponse` | Recurring period |
| `brand` | string | Brand |
| `accountType` | string | Account type |
| `sections[]` | `ComposedSectionResponse[]` | Invoice sections |
| `items[]` | `ComposedItemResponse[]` | Invoice items |
| `taxes[]` | `ComposedTaxResponse[]` | Invoice taxes |
| `amount` | `AmountResponse` | Tax-excluded/tax-included total |
| `balanceChanges[]` | `BalanceChangeResponse[]` | Balance changes |

### `ComposedItemResponse`

Useful V1 fields:

| Field | Type | Usage |
|-------|------|-------|
| `id` | uuid | Line identifier |
| `code` | string | Catalog/billing code |
| `description` | string | Customer/business label |
| `type` | string | Line type: recurring, one-off, usage, etc. to confirm |
| `defaultPrice` | integer cents | Default price |
| `amount` | `AmountResponse` | Composed tax-excluded/tax-included amount |
| `taxes[]` | `ComposedTaxResponse[]` | Associated taxes |
| `volume` | integer | Usage volume if applicable |
| `percentage` | number | For discount or tax if applicable |
| `effectiveAt` | date-time | One-off effective date |
| `frequency` | string | Recurring frequency |
| `referencePeriod` | `BillingPeriodResponse` | Reference period |
| `effectivePeriod` | `BillingPeriodResponse` | Effective period |
| `metadata` | object | Additional data to inspect on real examples |

### `AmountResponse`

| Field | Type | Usage |
|-------|------|-------|
| `amountTaxesExcluded` | number | Tax-excluded amount |
| `amountTaxesIncluded` | number | Tax-included amount |

Warning: `defaultPrice` is in cents, while `AmountResponse` is exposed as
`number`. Real examples will be needed to verify whether these amounts are in
euros or cents.

## Target Flow To Retrieve Two Invoices

Flow to validate with real examples:

1. Retrieve periods through `GET /bill-periods?year={year}`.
2. Choose the two comparable periods, for example the current month and the
   previous month.
3. Retrieve the `billRuns[]` associated with the periods.
4. For each bill run, call
   `GET /bill-runs/{bill_run_id}/bill-run-accounts/search?accountIdTerm={accountId}&billPeriodId={billPeriodId}`.
5. Extract `BillRunAccountResponse.id` as `billRunAccountId` and
   `invoiceNumber`.
6. Search invoice documents through
   `GET /bill-run-documents/search?billRunAccountId={billRunAccountId}` or
   `GET /bill-run-documents/search?accountId={accountId}&invoiceNumber={invoiceNumber}`.
7. Download the invoice PDF through
   `GET /bill-run-documents/{document_id}/download`.
8. Extract the PDF with `InvoicePdfExtractor`.
9. Use the extracted normalized JSON for the comparison engine.

## Mapping To The Voice Support Bot Domain

| Target Domain | Source |
|---------------|--------|
| `Invoice.number` | Extracted PDF / `BillRunDocumentResponse.filename` / `invoiceNumber` criterion |
| `Invoice.accountId` | `accountId` search criterion or extracted PDF |
| `Invoice.totalAmount` | Extracted PDF |
| `Invoice.period` | Extracted PDF |
| `InvoiceLine.id` | Internal extraction identifier |
| `InvoiceLine.label` | Extracted PDF |
| `InvoiceLine.type` | Post-extraction classification |
| `InvoiceLine.amount` | Extracted PDF |
| `InvoiceLine.volume` | Extracted PDF if present |
| `InvoiceLine.evidenceText` | Source PDF text fragment |
| `Evidence.source` | `billing-api` |
| `Evidence.documentId` | `BillRunDocumentResponse.id` |
| `Evidence.documentFilename` | `BillRunDocumentResponse.filename` |
| `Evidence.documentContentType` | `BillRunDocumentResponse.contentType` |

## Endpoints To Reproduce In The Mock

For a first API-compatible mock, reproduce only the `billing-api` side:

- `GET /bill-periods?year={year}`
- `GET /bill-periods/{bill_period_id}`
- `GET /bill-runs/{bill_run_id}/bill-run-accounts/search`
- `GET /bill-run-documents/search`
- `GET /bill-run-documents/{document_id}/download`

`GET /invoices/selected` is useful as a second step to verify the difference
between selected invoice and composed invoice, but it is not in the main V1
path.

## Open Questions

- Which exact flow makes it possible, from an `accountId`, to find the last two
  usable `billRunAccountId` values in `billing-api`?
- Which `contentType` values are returned by `/bill-run-documents/search` for
  invoices: PDF, CSV, JSON, other?
- Does the downloaded document contain only the customer PDF, or also a usable
  structured export?
- Which PDF extraction engine should be used to obtain text and tables with
  sufficient quality?
- Which reconciliation tolerance should be accepted between the sum of extracted
  lines and the invoice total?
- Which `BillRunAccountResponse.status` statuses indicate that an invoice is
  usable by the bot?
- Are discount, proration, adjustment and out-of-bundle lines distinguishable in
  the PDF alone, or must they be enriched with `discounts-service`,
  `adjustments-service` and `CDR`?
- Which standard Galaxion error format must be reproduced in the mock?

## Provisional Conclusion

Updated conclusion:

- use `billing-api` only for the Billing scope;
- reproduce the `bill-periods -> bill-runs -> bill-run-accounts ->
  bill-run-documents/search -> download` flow in the mock;
- add an `InvoicePdfExtractor` component to transform the PDF into structured
  JSON;
- do not implement `billing-service` endpoints in the V1 mock.

## Next Analysis

Analyze a real or anonymized example of the `billing-api` flow:

- available periods through `GET /bill-periods?year={year}`;
- bill runs associated with a period;
- `BillRunAccount` search for an `accountId`;
- document search through `GET /bill-run-documents/search` with one or more
  criteria;
- document download through `GET /bill-run-documents/{document_id}/download`;
- extraction of the PDF to the target JSON.

Then analyze `accounts-service`, `contracts-service`, `discounts-service` and
`CDR` for business causes.
