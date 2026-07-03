# Invoice PDF Extraction JSON Contract - Draft V1

## Objective

This document defines the draft JSON contract produced by `InvoicePdfExtractor`
after reading a Galaxion invoice PDF downloaded through `billing-api`.

The contract is intentionally deterministic. The PDF extractor is responsible
for parsing invoice amounts, invoice periods, sections, lines, taxes and
evidence into structured JSON. The LLM must not read the PDF directly to
calculate amounts or infer billing causes. It may only use this extracted JSON,
comparison-engine results, BSS evidence and approved response wording.

This draft must be validated against anonymized Galaxion PDFs before it becomes
a stable implementation contract.

## Scope

Included in V1:

- invoice identity and source document metadata;
- invoice-level dates, period, account and totals;
- normalized monetary sections and lines;
- tax details when visible in the PDF;
- extraction status and confidence;
- warnings for ambiguous or incomplete extraction;
- reconciliation between extracted line sums and invoice totals;
- source evidence for every customer-facing monetary line.

Out of scope for `InvoicePdfExtractor`:

- retrieving PDFs from Galaxion;
- authenticating the customer;
- comparing two invoices;
- deciding the business cause of a delta;
- calling LLMs;
- enriching lines with discounts, options, contract or CDR data.

Those responsibilities belong to the BSS adapter, comparison engine, evidence
enrichment layer and response generation layer.

## Source Systems

The V1 billing source is `billing-api`, not `billing-service`.

The expected upstream flow is:

```text
bill periods -> bill runs -> bill run accounts -> bill run documents -> PDF
```

The useful document endpoints are currently expected to be:

- `GET /bill-run-documents/search`
- `GET /bill-run-documents/{document_id}/download`

The downloaded PDF is the input to `InvoicePdfExtractor`. No structured invoice
line endpoint has been proven available for V1.

## Design Principles

- Amounts used for calculation are integer cents and use `*_cents` field names.
- Dates use ISO-8601 calendar dates: `YYYY-MM-DD`.
- Timestamps use ISO-8601 UTC instants.
- Field names are snake_case.
- Currency is explicit at invoice level.
- Every usable monetary line includes textual evidence from the PDF.
- Low-confidence extraction is preserved as warnings, not hidden.
- Reconciliation is a quality gate, not a business-cause decision.
- Unknown facts are represented as `null`, warnings or open questions, not
  inferred values.

## Top-Level JSON Shape

```json
{
  "schema_version": "invoice-extraction.v1",
  "extraction": {},
  "source_document": {},
  "invoice": {},
  "sections": [],
  "taxes": [],
  "reconciliation": {}
}
```

Top-level fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | yes | Contract version. V1 value: `invoice-extraction.v1`. |
| `extraction` | object | yes | Extractor metadata, status, confidence and warnings. |
| `source_document` | object | yes | Metadata linking the JSON back to the Galaxion document. |
| `invoice` | object | yes | Invoice identity, account, dates, period, currency and totals. |
| `sections` | array | yes | Monetary invoice sections and extracted lines. Empty only when unusable. |
| `taxes` | array | no | Tax table entries when visible or derivable from the PDF. |
| `reconciliation` | object | yes | Sum checks between extracted lines and invoice totals. |

## Extraction Metadata

```json
{
  "status": "parseable",
  "confidence": "high",
  "tool": "invoice-pdf-extractor",
  "tool_version": "0.1.0",
  "extracted_at": "2026-07-02T08:00:00Z",
  "warnings": []
}
```

### Extraction Statuses

| Status | Meaning | Downstream behavior |
|--------|---------|---------------------|
| `parseable` | The invoice has required identity fields, usable lines and successful reconciliation. | Full comparison is allowed. |
| `partial` | The invoice contains useful extracted data but has localized ambiguity or a small unreconciled remainder. | Compare confirmed lines only and surface uncertainty. |
| `unusable` | Required fields, totals, currency, period or usable lines are missing, or the PDF cannot be trusted. | Do not compare. Ask for another invoice, clarification or escalation. |

The most cautious status wins. If an invoice satisfies both a `partial` rule and
an `unusable` rule, the final status is `unusable`.

### `parseable`

An invoice can be `parseable` only when all conditions are true:

- `invoice.invoice_number` is present;
- `invoice.account_id` is present;
- `invoice.period.start` and `invoice.period.end` are present;
- `invoice.currency` is present and supported;
- `invoice.amounts.total_tax_included_cents` is present;
- at least one monetary line is included in reconciliation;
- `reconciliation.status = "reconciled"`;
- no warning with `severity = "error"` exists;
- no major PDF section is marked with `UNPARSED_SECTION`;
- all included lines have `extraction_confidence = "high"` or `"medium"`.

### `partial`

An invoice is `partial` when it can support a limited analysis but cannot support
a definitive global explanation.

Typical cases:

- reconciliation difference is above tolerance but below the material
  discrepancy threshold;
- one or more low-confidence lines were excluded;
- a non-critical section could not be parsed;
- tax details are ambiguous but tax-included amounts are usable;
- BSS enrichment is required before a billing cause can be confirmed.

The bot may explain confirmed parts but must keep the unexplained amount visible
until restitution.

### `unusable`

An invoice is `unusable` when the structured JSON is not reliable enough for
comparison.

Mandatory `unusable` cases:

- PDF is corrupted, protected, unreadable or not an invoice;
- invoice total is missing;
- currency is missing or unsupported;
- invoice number is missing;
- account identifier is missing;
- invoice period is missing and cannot be supplied by trusted BSS metadata;
- no usable monetary line exists;
- reconciliation is `not_applicable`;
- unreconciled difference reaches the material discrepancy threshold;
- PDF metadata conflicts with trusted `billing-api` metadata.

### Confidence

| Value | Meaning |
|-------|---------|
| `high` | Layout, labels, amounts and evidence are clear. |
| `medium` | Extraction is usable but one or more localized fields are uncertain. |
| `low` | Extraction is fragile and should not be used without human or fixture validation. |

A `parseable` invoice cannot have `confidence = "low"`.

## Source Document

```json
{
  "source": "billing-api",
  "document_id": "2f6098b1-83e4-4cc0-8a2a-4e7d3f70d5f5",
  "filename": "invoice-2026-06-100231079.pdf",
  "content_type": "application/pdf",
  "bill_period_id": "4b8a7f8f-6a2d-43c2-83b1-48ff3c2d9e5e",
  "bill_run_id": "7f62a6aa-3d14-49d4-95de-3b553f9cc6f0",
  "bill_run_account_id": "7a4e5d8e-2a84-41c7-9b42-7e9f1b4f014e"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | string | yes | Upstream source. V1 value: `billing-api`. |
| `document_id` | string | yes | Galaxion document identifier when available. |
| `filename` | string | no | Original document filename. |
| `content_type` | string | yes | Expected V1 value: `application/pdf`. |
| `bill_period_id` | string | no | Billing period identifier from Galaxion metadata. |
| `bill_run_id` | string | no | Bill run identifier from Galaxion metadata. |
| `bill_run_account_id` | string | no | Bill run account identifier from Galaxion metadata. |

If trusted metadata from `billing-api` disagrees with values read from the PDF,
the extractor must emit `METADATA_MISMATCH`. A material mismatch should make the
invoice `unusable`.

## Invoice Object

```json
{
  "invoice_number": "202606100231079",
  "account_id": "100231079",
  "customer_reference": "customer-eir-001",
  "brand": "Eir",
  "account_type": "B2C",
  "invoice_date": "2026-07-01",
  "due_date": "2026-07-15",
  "period": {
    "start": "2026-06-01",
    "end": "2026-06-30"
  },
  "currency": "EUR",
  "amounts": {
    "total_tax_included_cents": 6840,
    "total_tax_excluded_cents": 5561,
    "tax_total_cents": 1279,
    "previous_balance_cents": 0,
    "payments_received_cents": 0,
    "amount_due_cents": 6840
  }
}
```

Required fields for a `parseable` invoice:

- `invoice_number`
- `account_id`
- `period.start`
- `period.end`
- `currency`
- `amounts.total_tax_included_cents`

`amount_due_cents` may differ from `total_tax_included_cents` when previous
balances, payments, credit notes or collections amounts are visible. In V1,
reconciliation uses `total_tax_included_cents` as the invoice-period amount,
unless real PDFs prove another field is the correct customer-facing total.

## Sections And Lines

`sections` groups visible PDF sections such as monthly charges, usage, one-off
charges, discounts or taxes. Section labels preserve the visible wording where
possible.

```json
{
  "id": "section-subscriptions",
  "label": "Monthly charges",
  "category": "subscription",
  "total_tax_included_cents": 2999,
  "lines": [
    {
      "id": "line-001",
      "label": "Mobile plan 100GB",
      "normalized_label": "mobile_plan_100gb",
      "category": "subscription",
      "amount_tax_included_cents": 2999,
      "amount_tax_excluded_cents": 2438,
      "tax_cents": 561,
      "tax_rate": "23.00",
      "quantity": "1",
      "period": {
        "start": "2026-06-01",
        "end": "2026-06-30"
      },
      "evidence": {
        "page": 2,
        "text": "Mobile plan 100GB 01 Jun - 30 Jun EUR 29.99",
        "bbox": null
      },
      "extraction_confidence": "high",
      "warnings": []
    }
  ]
}
```

### Line Categories

| Category | Usage |
|----------|-------|
| `subscription` | Recurring subscription or base plan charge. |
| `discount` | Discount, promotion or negative commercial gesture. |
| `usage` | Included or ordinary usage line. |
| `overage` | Out-of-bundle usage. |
| `option` | Option, add-on or additional service. |
| `prorata` | Partial-period billing. |
| `one_off` | Activation fee, equipment fee or other one-off charge. |
| `adjustment` | Billing adjustment, correction or regularization. |
| `tax` | Tax when displayed as an invoice line. |
| `payment` | Payment or credit displayed in the invoice summary. |
| `previous_balance` | Prior balance carried into the document. |
| `other` | Monetary line not classified by V1 rules. |

### Evidence

Every line included in reconciliation must have evidence.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `page` | integer | yes | One-based PDF page number. |
| `text` | string | yes | Short source text sufficient for audit or fixture review. |
| `bbox` | object/null | no | Optional bounding box if the extractor can provide coordinates. |

The evidence text must be short enough for logs and test fixtures, and must not
contain unnecessary customer personal data when a narrower line excerpt is
available.

## Taxes

`taxes` captures visible tax summary rows. It is used for audit and diagnostics,
not as the primary comparison basis in V1.

```json
{
  "label": "VAT",
  "rate": "23.00",
  "taxable_amount_cents": 5561,
  "tax_amount_cents": 1279,
  "evidence": {
    "page": 3,
    "text": "VAT 23% EUR 12.79",
    "bbox": null
  }
}
```

If taxes are included in line amounts but not visible as a separate table,
`taxes` may be empty. The extractor should emit `MISSING_TAX_BREAKDOWN` only
when the absence prevents reconciliation or audit.

## Reconciliation

Reconciliation checks that the extracted monetary lines form a coherent invoice.
It does not explain why a charge changed between two invoices.

```json
{
  "status": "reconciled",
  "basis": "tax_included",
  "included_line_ids": ["line-001", "line-002"],
  "excluded_line_ids": [],
  "line_sum_tax_included_cents": 6840,
  "invoice_total_tax_included_cents": 6840,
  "difference_cents": 0,
  "tolerance_cents": 1,
  "unexplained_amount_cents": 0,
  "notes": []
}
```

### Reconciliation Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | enum | yes | `reconciled`, `unreconciled` or `not_applicable`. |
| `basis` | enum | yes | V1 value: `tax_included`. |
| `included_line_ids` | string[] | yes | Monetary lines included in the sum. |
| `excluded_line_ids` | string[] | yes | Monetary lines explicitly excluded from the sum. |
| `line_sum_tax_included_cents` | integer | yes | Sum of retained tax-included lines. |
| `invoice_total_tax_included_cents` | integer/null | yes | Invoice total used as target for reconciliation. |
| `difference_cents` | integer/null | yes | `invoice_total_tax_included_cents - line_sum_tax_included_cents`. |
| `tolerance_cents` | integer | yes | Accepted rounding tolerance. Initial value: `1`. |
| `unexplained_amount_cents` | integer/null | yes | Amount that remains unaccounted for by included lines. |
| `notes` | string[] | no | Debug or QA notes. Must not replace warnings. |

### Included Lines

Include these lines when they are monetary and at least medium confidence:

- subscriptions;
- options and add-ons;
- usage and overage;
- discounts;
- one-off fees;
- proratas;
- adjustments;
- tax lines if the invoice total adds them as independent monetary lines.

### Excluded Lines

Exclude these lines from reconciliation:

- subtotals, totals and amount-due summaries;
- previous balance when reconciling the current invoice period;
- payments already received;
- duplicate candidates;
- low-confidence lines;
- non-monetary descriptive rows;
- unparsed sections.

Every excluded monetary line must appear in `excluded_line_ids`. If excluding it
can change the customer explanation, it must also produce a warning.

### Formula

```text
line_sum_tax_included_cents = sum(included line amount_tax_included_cents)
difference_cents = invoice_total_tax_included_cents - line_sum_tax_included_cents
```

Rules:

- `status = "reconciled"` when `abs(difference_cents) <= tolerance_cents`.
- `status = "unreconciled"` when the total and lines exist but the difference is
  above tolerance.
- `status = "not_applicable"` when the invoice total or usable lines are missing.
- `unexplained_amount_cents = abs(difference_cents)` for unreconciled invoices.
- `unexplained_amount_cents = 0` for reconciled invoices.
- `unexplained_amount_cents = null` when reconciliation is not applicable.

Initial material discrepancy threshold:

- `500` cents; or
- `5%` of `invoice_total_tax_included_cents`;
- whichever is smaller.

This threshold is a draft default and must be validated with real PDFs.

### Impact On Extraction Status

| Reconciliation result | Extraction status | Behavior |
|-----------------------|-------------------|----------|
| `reconciled` and no blocking warnings | `parseable` | Full comparison allowed. |
| `reconciled` with non-blocking warnings | `partial` or `parseable` | Depends on warning severity and line confidence. |
| `unreconciled` below material threshold | `partial` | Compare confirmed lines and expose remainder. |
| `unreconciled` at or above material threshold | `unusable` by default | Do not provide a definitive comparison. |
| `not_applicable` | `unusable` | No comparison. Clarification or escalation. |

## Warning Model

Warnings appear at `extraction.warnings` for invoice-wide issues and at
`sections[].lines[].warnings` for line-local issues.

```json
{
  "code": "UNRECONCILED_TOTAL",
  "severity": "warning",
  "message": "Line sum differs from invoice total by EUR 2.50",
  "page": 3,
  "line_id": null
}
```

Warning fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | enum | yes | Stable machine-readable warning code. |
| `severity` | enum | yes | `info`, `warning` or `error`. |
| `message` | string | yes | Human-readable QA/debug message. |
| `page` | integer/null | no | PDF page where the issue was observed. |
| `line_id` | string/null | no | Related line when applicable. |

### Warning Codes

| Code | Meaning | Typical effect |
|------|---------|----------------|
| `PDF_UNREADABLE` | PDF is encrypted, corrupted or text cannot be extracted. | `unusable` |
| `NOT_AN_INVOICE` | Document does not look like a Galaxion invoice. | `unusable` |
| `MISSING_INVOICE_NUMBER` | Invoice number cannot be found. | `unusable` |
| `MISSING_ACCOUNT_ID` | Account identifier cannot be found. | `unusable` |
| `MISSING_PERIOD` | Invoice period is missing or ambiguous. | `unusable` unless trusted metadata supplies it |
| `MISSING_TOTAL` | Invoice total cannot be found. | `unusable` |
| `UNKNOWN_CURRENCY` | Currency is missing or unsupported. | `unusable` |
| `METADATA_MISMATCH` | PDF identity disagrees with `billing-api` metadata. | `partial` or `unusable` |
| `UNRECONCILED_TOTAL` | Extracted lines do not sum to invoice total. | `partial` or `unusable` |
| `LOW_CONFIDENCE_LINE` | A monetary line was extracted with low confidence. | Exclude line, mark invoice `partial` |
| `UNPARSED_SECTION` | A visible PDF section could not be transformed into lines. | `partial` or `unusable` |
| `DUPLICATE_LINE_CANDIDATE` | Two candidate lines may represent the same charge. | Exclude candidate or mark `partial` |
| `MISSING_TAX_BREAKDOWN` | Tax table or per-line tax is absent or ambiguous. | Usually `partial` only if totals reconcile |
| `AMBIGUOUS_AMOUNT_SIGN` | The extractor cannot tell whether an amount is debit or credit. | `partial` or line exclusion |
| `AMBIGUOUS_LINE_PERIOD` | A line period is unclear. | Keep invoice usable only if amount is clear |
| `UNCLASSIFIED_LINE` | A monetary line cannot be mapped to a V1 category. | Usually `partial`; category becomes `other` |

Warnings with `severity = "error"` block `parseable`.

## Full Example

```json
{
  "schema_version": "invoice-extraction.v1",
  "extraction": {
    "status": "parseable",
    "confidence": "high",
    "tool": "invoice-pdf-extractor",
    "tool_version": "0.1.0",
    "extracted_at": "2026-07-02T08:00:00Z",
    "warnings": []
  },
  "source_document": {
    "source": "billing-api",
    "document_id": "2f6098b1-83e4-4cc0-8a2a-4e7d3f70d5f5",
    "filename": "invoice-2026-06-100231079.pdf",
    "content_type": "application/pdf",
    "bill_period_id": "4b8a7f8f-6a2d-43c2-83b1-48ff3c2d9e5e",
    "bill_run_id": "7f62a6aa-3d14-49d4-95de-3b553f9cc6f0",
    "bill_run_account_id": "7a4e5d8e-2a84-41c7-9b42-7e9f1b4f014e"
  },
  "invoice": {
    "invoice_number": "202606100231079",
    "account_id": "100231079",
    "customer_reference": "customer-eir-001",
    "brand": "Eir",
    "account_type": "B2C",
    "invoice_date": "2026-07-01",
    "due_date": "2026-07-15",
    "period": {
      "start": "2026-06-01",
      "end": "2026-06-30"
    },
    "currency": "EUR",
    "amounts": {
      "total_tax_included_cents": 3149,
      "total_tax_excluded_cents": 2560,
      "tax_total_cents": 589,
      "previous_balance_cents": 0,
      "payments_received_cents": 0,
      "amount_due_cents": 3149
    }
  },
  "sections": [
    {
      "id": "section-subscriptions",
      "label": "Monthly charges",
      "category": "subscription",
      "total_tax_included_cents": 2999,
      "lines": [
        {
          "id": "line-001",
          "label": "Mobile plan 100GB",
          "normalized_label": "mobile_plan_100gb",
          "category": "subscription",
          "amount_tax_included_cents": 2999,
          "amount_tax_excluded_cents": 2438,
          "tax_cents": 561,
          "tax_rate": "23.00",
          "quantity": "1",
          "period": {
            "start": "2026-06-01",
            "end": "2026-06-30"
          },
          "evidence": {
            "page": 2,
            "text": "Mobile plan 100GB 01 Jun - 30 Jun EUR 29.99",
            "bbox": null
          },
          "extraction_confidence": "high",
          "warnings": []
        }
      ]
    },
    {
      "id": "section-one-off",
      "label": "One-off charges and adjustments",
      "category": "one_off",
      "total_tax_included_cents": 150,
      "lines": [
        {
          "id": "line-002",
          "label": "Option activation prorata",
          "normalized_label": "option_activation_prorata",
          "category": "prorata",
          "amount_tax_included_cents": 150,
          "amount_tax_excluded_cents": 122,
          "tax_cents": 28,
          "tax_rate": "23.00",
          "quantity": "1",
          "period": {
            "start": "2026-06-14",
            "end": "2026-06-30"
          },
          "evidence": {
            "page": 2,
            "text": "Option activation prorata 14 Jun - 30 Jun EUR 1.50",
            "bbox": null
          },
          "extraction_confidence": "medium",
          "warnings": []
        }
      ]
    }
  ],
  "taxes": [
    {
      "label": "VAT",
      "rate": "23.00",
      "taxable_amount_cents": 2560,
      "tax_amount_cents": 589,
      "evidence": {
        "page": 3,
        "text": "VAT 23% EUR 5.89",
        "bbox": null
      }
    }
  ],
  "reconciliation": {
    "status": "reconciled",
    "basis": "tax_included",
    "included_line_ids": ["line-001", "line-002"],
    "excluded_line_ids": [],
    "line_sum_tax_included_cents": 3149,
    "invoice_total_tax_included_cents": 3149,
    "difference_cents": 0,
    "tolerance_cents": 1,
    "unexplained_amount_cents": 0,
    "notes": []
  }
}
```

## Comparison Preconditions

When comparing two invoices:

| Previous invoice | Current invoice | Decision |
|------------------|-----------------|----------|
| `parseable` | `parseable` | Full deterministic comparison allowed. |
| `parseable` | `partial` | Compare confirmed lines only; expose current invoice uncertainty. |
| `partial` | `parseable` | Compare confirmed lines only; expose previous invoice uncertainty. |
| `partial` | `partial` | Limited comparison; escalation recommended for certainty. |
| `unusable` | any status | Comparison forbidden. |
| any status | `unusable` | Comparison forbidden. |

The comparison engine must never treat `unexplained_amount_cents` as a business
cause. It is an extraction-quality signal.

## Restitution Rules

Customer-facing answers must follow these rules:

- If both invoices are `parseable`, the bot may state the global delta and
  confirmed causes.
- If either invoice is `partial`, the bot must separate confirmed causes from
  unexplained remainder.
- If either invoice is `unusable`, the bot must not compare invoice amounts.
- The bot must cite line evidence or BSS evidence for every confirmed cause.
- The bot must not say that an amount changed because of reconciliation drift,
  missing extraction or another quality warning.

Example wording for a partial invoice:

> I can confirm EUR 66.90 from extracted invoice lines, but EUR 2.50 remains
> unexplained by the PDF extraction. I can continue with the confirmed lines or
> escalate this invoice for manual validation.

## Questions To Validate With Anonymized PDFs

### PDF Layout And Extraction

- Are invoice sections stable across brands, account types and billing months?
- Do Galaxion PDFs use multi-column tables, merged rows or repeated headers?
- Are line labels and amounts extractable as text, or are some PDFs image-based?
- Are page numbers and bounding boxes needed for audit, or is text evidence
  enough for V1?
- Are there footer/header amounts that can be mistaken for invoice lines?

### Amounts And Totals

- Which PDF total is the customer-facing amount for comparison:
  `total_tax_included`, `amount_due`, or another label?
- Does the invoice total include previous balance, payments or collection
  amounts?
- Are amounts represented with commas, periods, currency symbols or localized
  labels that affect parsing?
- Are negative amounts printed with a minus sign, parentheses, "CR", or another
  credit marker?
- What rounding tolerance is needed for tax and subtotal reconciliation?

### Taxes

- Do lines expose tax-included, tax-excluded and tax amount values?
- Is there always a tax summary table?
- Can multiple tax rates appear on a single invoice?
- Are tax lines included in section totals or only in the invoice summary?

### Billing Causes

- How do discounts appear: negative lines, section-level reductions, or separate
  summary entries?
- Do expired discounts include enough PDF evidence, or must BSS enrichment
  always confirm them?
- Do prorata lines expose explicit start and end dates?
- Do option activations and cancellations appear as distinct line categories?
- Do out-of-bundle charges include volume, destination, period or only an amount?
- Are adjustments and commercial gestures distinguishable in PDF wording?

### Galaxion Metadata

- Does `bill-run-documents/search` always return a single invoice PDF per account
  and billing period?
- Is `contentType` always `application/pdf`?
- Which identifiers are stable across the PDF and `billing-api`: invoice number,
  account ID, bill period ID, bill run ID or bill run account ID?
- What should happen when PDF invoice metadata disagrees with `billing-api`
  metadata?

### Security And Fixtures

- Which customer fields must be removed or masked in anonymized PDF fixtures?
- Can evidence snippets include account numbers or customer references?
- Which fields are allowed in logs and regression snapshots?
- Are there invoices with sensitive call-detail or usage-detail rows that need a
  stricter fixture policy?

## Acceptance Criteria For First Fixture Validation

The first anonymized PDF fixture set should allow the team to confirm:

- the extractor can produce valid `invoice-extraction.v1` JSON;
- all parseable invoices reconcile within the selected tolerance;
- every included monetary line has evidence;
- the status decision matches the decision matrix;
- warning codes are sufficient for observed ambiguities;
- comparison can explain a visible invoice delta without LLM calculation;
- unknown PDF fields are captured as open questions instead of hidden
  assumptions.

## Open Assumptions

- `EUR` is the initial currency for Galaxion V1 examples.
- `tax_included` is the V1 reconciliation basis because customer explanations
  focus on billed amounts.
- A one-cent tolerance is sufficient unless real PDFs prove otherwise.
- A material discrepancy starts at `500` cents or `5%` of invoice total,
  whichever is smaller.
- `billing-api` metadata is more trusted than text extracted from the PDF when
  identity fields conflict.

