# Invoice PDF Extraction JSON - Draft V1

## Objective

This document defines the first target JSON produced by `InvoicePdfExtractor`
from a Galaxion invoice PDF.

The format will be adjusted after reviewing anonymized PDFs, but it should
already act as the contract between:

- the V1 BSS mock;
- regression fixtures;
- the deterministic comparison engine;
- the explanation generator with evidence.

The LLM must never read the PDF to calculate amounts. It only receives this
normalized JSON, the comparison-engine results, and cited evidence.

## Principles

- Amounts are stored as **integer cents** (`*_cents`) to avoid rounding errors.
- Currency is explicit at invoice level (`currency`).
- Every usable line carries minimal textual evidence (`evidence`).
- Every extraction ambiguity is exposed through `warnings`.
- The global extraction status decides whether the invoice can enter the
  comparison engine.

## Extraction Statuses

| Status | Meaning | Bot Usage |
|--------|---------|-----------|
| `parseable` | Total, period and main lines were extracted and reconciled | Comparison allowed |
| `partial` | Some lines or sections are uncertain, but part of the invoice is usable | Cautious comparison with unexplained remainder |
| `unusable` | Total, period, account or minimum lines are missing or inconsistent | No comparison, clarification or escalation |

### `parseable`

An invoice is `parseable` only when all the following conditions are true:

- minimum required fields are present;
- at least one usable monetary line is extracted;
- `reconciliation.status = reconciled`;
- no `error` warning is present;
- no major PDF section is marked as `UNPARSED_SECTION`;
- lines included in reconciliation have `high` or `medium` confidence.

Product effect:

- the engine can compare this invoice with another `parseable` invoice;
- the bot can state the global delta and confirmed causes;
- evidence can be exposed without a global uncertainty disclaimer.

### `partial`

An invoice is `partial` when it contains enough information to help the analysis,
but not enough to fully conclude.

Typical cases:

- `reconciliation.status = unreconciled`, with a difference below the material
  discrepancy threshold;
- one or more lines are excluded because of low confidence;
- a non-critical section is not parsed;
- main amounts are present, but some taxes, discounts or line periods are
  ambiguous;
- external BSS enrichment is needed to confirm a cause.

Product effect:

- the engine can compare confirmed lines;
- `unexplained_amount_cents` must remain visible until restitution;
- the bot must distinguish confirmed causes from the unexplained remainder;
- the bot must not present the global delta as fully explained;
- escalation must be offered if the user asks for certainty.

### `unusable`

An invoice is `unusable` when the system cannot use it as a reliable comparison
basis.

Mandatory `unusable` cases:

- invoice total is missing;
- currency is unknown;
- `account_id` or `invoice_number` is missing;
- invoice period is missing and not provided by the BSS;
- no usable monetary line exists;
- `reconciliation.status = not_applicable`;
- `reconciliation.status = unreconciled` with a material discrepancy;
- PDF is unreadable, protected, corrupted, or not actually an invoice;
- major inconsistency exists between the PDF and `billing-api` metadata.

Product effect:

- the engine must not compare this invoice;
- the bot must explain that the invoice cannot be processed automatically;
- the bot must ask for clarification, try another invoice/document, or offer
  escalation.

### Decision Matrix

| Signal | Target Status |
|--------|---------------|
| Minimum fields present + reconciliation OK | `parseable` |
| Minimum fields present + small reconciliation failure | `partial` |
| Minimum fields present + minor unparsed section | `partial` |
| Minimum fields present + low-confidence line excluded | `partial` |
| Total missing | `unusable` |
| Currency missing or unknown | `unusable` |
| No usable monetary line | `unusable` |
| PDF corrupted / protected / not an invoice | `unusable` |
| Material reconciliation discrepancy | `unusable` by default |

The most cautious status wins: if an invoice matches both a `partial` criterion
and an `unusable` criterion, it must be `unusable`.

### Global Confidence

`extraction.confidence` complements the status but does not replace it.

| Confidence | Usage |
|------------|-------|
| `high` | Stable extraction, clear textual evidence, well-reconciled lines |
| `medium` | Usable extraction with localized ambiguity |
| `low` | Fragile extraction; in practice `partial` or `unusable` |

A `parseable` invoice cannot have `confidence = low`.

### Behavior When Comparing Two Invoices

The comparison engine must evaluate the invoice pair:

| Invoice A | Invoice B | Decision |
|-----------|-----------|----------|
| `parseable` | `parseable` | Full comparison allowed |
| `parseable` | `partial` | Cautious comparison, unexplained remainder required |
| `partial` | `partial` | Compare confirmed lines only, escalation recommended |
| `unusable` | any status | Comparison forbidden |
| any status | `unusable` | Comparison forbidden |

## Target JSON

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
    "bill_run_account_id": "7a4e5d8e-2a84-41c7-9b42-7e9f1b4f014e",
    "bill_period_id": "4b8a7f8f-6a2d-43c2-83b1-48ff3c2d9e5e"
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
      "total_tax_included_cents": 6840,
      "total_tax_excluded_cents": 5561,
      "tax_total_cents": 1279,
      "previous_balance_cents": 0,
      "payments_received_cents": 0,
      "amount_due_cents": 6840
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
      "taxable_amount_cents": 5561,
      "tax_amount_cents": 1279,
      "evidence": {
        "page": 3,
        "text": "VAT 23% EUR 12.79",
        "bbox": null
      }
    }
  ],
  "reconciliation": {
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
}
```

## Minimum Required Fields

An extraction can be `parseable` only if these fields are present:

- `invoice.invoice_number`
- `invoice.account_id`
- `invoice.period.start`
- `invoice.period.end`
- `invoice.currency`
- `invoice.amounts.total_tax_included_cents`
- `sections[].lines[]` with at least one usable monetary line
- `reconciliation.status`

If any of these fields is missing, the status must be `partial` or `unusable`.

## V1 Line Categories

| Category | Usage |
|----------|-------|
| `subscription` | Recurring subscription |
| `discount` | Discount, promotion, negative commercial gesture |
| `usage` | Included or billable usage |
| `overage` | Out-of-bundle usage |
| `option` | Option or additional service |
| `prorata` | Partial-period billing |
| `one_off` | One-off fee |
| `adjustment` | Adjustment or correction |
| `tax` | Tax if present as an invoice line |
| `payment` | Payment or credit if exposed on the invoice |
| `other` | Unclassified monetary line |

These categories feed the comparison engine. They can be enriched with
additional BSS data (`discounts-service`, CDR, account events) to confirm a
business cause.

## Warnings

Warnings are normalized so the engine and bot can stay cautious.

| Code | Meaning | Expected Effect |
|------|---------|-----------------|
| `MISSING_PERIOD` | Invoice period is missing or ambiguous | `unusable` unless BSS provides the period |
| `MISSING_TOTAL` | Invoice total cannot be found | `unusable` |
| `UNRECONCILED_TOTAL` | Line sum differs from total beyond tolerance | `partial` or `unusable` depending on discrepancy |
| `LOW_CONFIDENCE_LINE` | A monetary line is extracted with low confidence | Exclude line or mark cause uncertain |
| `UNPARSED_SECTION` | A PDF section was not transformed into lines | Expose an unexplained remainder |
| `DUPLICATE_LINE_CANDIDATE` | Two lines seem to represent the same charge | Request validation / mark partial |
| `UNKNOWN_CURRENCY` | Currency is missing or unknown | `unusable` |

Example:

```json
{
  "code": "UNRECONCILED_TOTAL",
  "severity": "warning",
  "message": "Line sum differs from invoice total by EUR 2.50",
  "page": 3
}
```

## Reconciliation Rules

Reconciliation decides whether the extracted JSON can be used as a calculation
basis by the comparison engine. It does not decide business causes yet: it only
checks that extracted amounts form a coherent invoice.

### Reconciliation Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | enum | `reconciled`, `unreconciled`, `not_applicable` |
| `basis` | enum | Calculation basis used: `tax_included` in V1 |
| `included_line_ids` | string[] | Monetary lines included in the sum |
| `excluded_line_ids` | string[] | Ignored lines: low confidence, duplicate, total, payment, previous balance |
| `line_sum_tax_included_cents` | integer | Tax-included sum of included lines |
| `invoice_total_tax_included_cents` | integer | Extracted invoice tax-included total |
| `difference_cents` | integer | Invoice total minus line sum |
| `tolerance_cents` | integer | Maximum accepted difference |
| `unexplained_amount_cents` | integer | Amount not explained by included lines |
| `notes` | string[] | Details useful for debug or QA |

`basis` remains fixed to `tax_included` for V1 because customer questions are
about the billed amount including tax. Tax-excluded amounts and tax details are
kept for audit and diagnostics, but they do not drive customer-facing comparison
until real PDFs are reviewed.

### Included And Excluded Lines

Include in `included_line_ids`:

- subscription lines;
- options and services;
- out-of-bundle usage;
- discounts;
- one-off fees;
- proratas;
- adjustments;
- taxes if they appear as autonomous invoice lines and the invoice total adds
  them this way.

Exclude from `included_line_ids`:

- total or subtotal lines;
- previous balance;
- payments already received;
- amount due if it is a summary;
- likely duplicates;
- lines with `extraction_confidence = low`;
- non-monetary lines;
- sections explicitly marked as unparsed.

Every excluded line must appear in `excluded_line_ids` and produce a warning if
its exclusion can change the customer explanation.

### Formula

- `line_sum_tax_included_cents` sums all retained monetary lines.
- `difference_cents = invoice_total_tax_included_cents - line_sum_tax_included_cents`.
- `status = reconciled` if `abs(difference_cents) <= tolerance_cents`.
- `status = unreconciled` if the difference exceeds tolerance.
- `status = not_applicable` if the invoice total or minimum lines are missing.
- `unexplained_amount_cents` carries the unreconciled difference the bot must
  present as uncertain or unexplained.

Initial proposed tolerance: `1` cent. This can be adjusted if PDFs round taxes or
subtotals differently.

### Impact On Extraction Status

| Reconciliation | Possible Extraction Status | Expected Behavior |
|----------------|----------------------------|-------------------|
| `reconciled` | `parseable` | Invoice can be compared normally |
| `unreconciled` with small discrepancy explained by minor warnings | `partial` | Comparison possible, but the bot exposes an unexplained remainder |
| `unreconciled` with material discrepancy | `partial` or `unusable` | No definitive conclusion on the global delta |
| `not_applicable` | `unusable` | Clarification or escalation, no comparison |

Initial material discrepancy threshold: `500` cents or more than `5%` of the
invoice total, whichever is smaller. This threshold is only a starting point for
the mock and must be validated against real PDFs.

### Examples

#### Reconciled Invoice

```json
{
  "status": "reconciled",
  "basis": "tax_included",
  "included_line_ids": ["line-001", "line-002", "line-003"],
  "excluded_line_ids": [],
  "line_sum_tax_included_cents": 6840,
  "invoice_total_tax_included_cents": 6840,
  "difference_cents": 0,
  "tolerance_cents": 1,
  "unexplained_amount_cents": 0,
  "notes": []
}
```

#### Partially Reconciled Invoice

```json
{
  "status": "unreconciled",
  "basis": "tax_included",
  "included_line_ids": ["line-001", "line-002"],
  "excluded_line_ids": ["line-009"],
  "line_sum_tax_included_cents": 6590,
  "invoice_total_tax_included_cents": 6840,
  "difference_cents": 250,
  "tolerance_cents": 1,
  "unexplained_amount_cents": 250,
  "notes": [
    "Line line-009 excluded because extraction confidence is low"
  ]
}
```

In this case, the bot can explain confirmed causes but must say that `250` cents
remain unconfirmed.

#### Unusable Invoice

```json
{
  "status": "not_applicable",
  "basis": "tax_included",
  "included_line_ids": [],
  "excluded_line_ids": [],
  "line_sum_tax_included_cents": 0,
  "invoice_total_tax_included_cents": null,
  "difference_cents": null,
  "tolerance_cents": 1,
  "unexplained_amount_cents": null,
  "notes": [
    "Invoice total could not be extracted"
  ]
}
```

In this case, `extraction.status` must be `unusable`.

### Spoken Restitution Rule

The bot must never present `difference_cents` or `unexplained_amount_cents` as a
business cause. These are extraction-quality indicators. The expected wording is:

> I was able to confirm EUR 66.90 of invoice lines, but EUR 2.50 remains
> unexplained by the extracted invoice data.

If `reconciliation.status` is not `reconciled`, every explanation must include
an uncertainty statement or offer escalation depending on the discrepancy
threshold.

## Questions To Validate With Anonymized PDFs

- Do Galaxion PDFs expose tax-excluded, tax-included and tax amounts per line?
- Do discounts appear as negative lines or section reductions?
- Do proratas expose an explicit period per line?
- Do out-of-bundle lines carry usable volume or only an amount?
- Are invoice sections stable from one month to another?
- Do PDFs contain multi-column areas or tables that are hard to extract?
- Is the `/bill-run-documents/download` `contentType` always PDF, or can it be
  CSV/ZIP/another format?
