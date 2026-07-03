# Invoice PDF Extraction JSON Contract - Draft V1

## Purpose

This document defines the draft technical contract for JSON produced by
`InvoicePdfExtractor` from Galaxion invoice PDFs.

The contract is intended for:

- the local BSS mock and future Galaxion adapter;
- deterministic invoice comparison;
- regression fixtures built from anonymized PDFs;
- customer-facing explanation generation with traceable evidence.

The PDF is an extraction source, not a reasoning source. The bot must not ask an
LLM to read a PDF and calculate billing amounts. Amounts must first be extracted
into this JSON, reconciled, and then compared by deterministic code.

## Design Principles

- Monetary values are integer cents in fields ending with `_cents`.
- The invoice currency is explicit and applies to every amount unless a line
  overrides it.
- Every monetary line used by the comparison engine carries page-level evidence.
- Extraction uncertainty is represented as structured `warnings`, not hidden in
  free text.
- The global `extraction.status` controls whether the invoice can be compared.
- The reconciliation result checks arithmetic consistency only; it does not
  decide the business cause of a bill change.

## Status Model

### `parseable`

The invoice is reliable enough for normal comparison.

Required signals:

- all minimum required fields are present;
- at least one usable monetary line was extracted;
- `reconciliation.status` is `reconciled`;
- there is no warning with `severity = "error"`;
- all lines included in reconciliation have `high` or `medium` confidence;
- no major invoice section is marked as unparsed.

Allowed downstream behavior:

- compare this invoice with another `parseable` invoice;
- state the global delta as reconciled;
- explain confirmed line-level causes using extracted evidence.

### `partial`

The invoice contains useful information but not enough to fully conclude.

Typical signals:

- minimum fields are present, but reconciliation has a small discrepancy;
- a non-critical PDF section could not be parsed;
- one or more lines were excluded because confidence is low;
- taxes, discounts, prorata dates, or line grouping are ambiguous;
- BSS enrichment is needed to confirm the business cause.

Allowed downstream behavior:

- compare confirmed lines only;
- keep `unexplained_amount_cents` visible in the result;
- use uncertainty wording in the bot response;
- offer escalation when the customer asks for certainty.

### `unusable`

The invoice is not reliable enough for automated comparison.

Mandatory `unusable` cases:

- the invoice total is missing;
- currency is missing or unknown;
- `invoice_number` or `account_id` is missing;
- the invoice period is missing and cannot be supplied by Galaxion metadata;
- no usable monetary line exists;
- `reconciliation.status` is `not_applicable`;
- reconciliation has a material unexplained discrepancy;
- the PDF is corrupted, protected, unreadable, or not an invoice;
- PDF identifiers conflict with `billing-api` document metadata.

Allowed downstream behavior:

- do not compare this invoice;
- explain that automatic analysis is not possible;
- ask for another document, missing context, or human escalation.

## Status Decision Matrix

| Signal | Extraction Status |
|---|---|
| Minimum fields present and reconciliation OK | `parseable` |
| Minimum fields present and small reconciliation failure | `partial` |
| Minor unparsed section with explainable remainder | `partial` |
| Low-confidence monetary line excluded | `partial` |
| Total missing | `unusable` |
| Currency missing or unknown | `unusable` |
| No usable monetary line | `unusable` |
| PDF corrupted, protected, or not an invoice | `unusable` |
| Material reconciliation discrepancy | `unusable` by default |

The most cautious status wins. If an invoice matches both a `partial` criterion
and an `unusable` criterion, the final status is `unusable`.

## JSON Shape

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
    "document_id": "doc-2026-06-0001",
    "filename": "invoice-2026-06-100231079.pdf",
    "content_type": "application/pdf",
    "bill_period_id": "period-2026-06",
    "bill_run_id": "bill-run-2026-06",
    "bill_run_account_id": "bill-run-account-100231079"
  },
  "invoice": {
    "invoice_number": "202606100231079",
    "account_id": "100231079",
    "customer_reference": "customer-anonymized-001",
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
      "id": "section-adjustments",
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

An extraction can be `parseable` only when these fields exist:

- `schema_version`;
- `extraction.status`;
- `invoice.invoice_number`;
- `invoice.account_id`;
- `invoice.period.start`;
- `invoice.period.end`;
- `invoice.currency`;
- `invoice.amounts.total_tax_included_cents`;
- at least one `sections[].lines[]` monetary line included in reconciliation;
- `reconciliation.status`;
- `reconciliation.difference_cents`.

If any required field is missing, the extractor must downgrade the status to
`partial` or `unusable` and add a warning explaining why.

## Line Categories

| Category | Meaning |
|---|---|
| `subscription` | Recurring subscription or plan charge |
| `discount` | Promotion, recurring discount, credit, or commercial gesture |
| `usage` | Included or metered usage line |
| `overage` | Out-of-bundle usage |
| `option` | Add-on, option, or additional service |
| `prorata` | Partial-period charge or credit |
| `one_off` | Activation, installation, equipment, or one-time fee |
| `adjustment` | Correction, regularization, or manual adjustment |
| `tax` | Tax line when tax is represented as a billable line |
| `payment` | Payment received or balance movement shown on the invoice |
| `other` | Monetary line that cannot yet be classified |

Categories are used by the comparison engine to group deltas. BSS enrichment may
later confirm the business cause, for example an expired discount, option
activation, offer change, or out-of-bundle event.

## Warning Model

Warnings are structured records:

```json
{
  "code": "UNRECONCILED_TOTAL",
  "severity": "warning",
  "message": "Line sum differs from invoice total by EUR 2.50",
  "page": 3,
  "line_id": null
}
```

| Code | Severity | Meaning | Expected Effect |
|---|---|---|---|
| `MISSING_PERIOD` | `error` | Invoice period is missing or ambiguous | `unusable` unless metadata supplies the period |
| `MISSING_TOTAL` | `error` | Invoice total cannot be extracted | `unusable` |
| `UNKNOWN_CURRENCY` | `error` | Currency is missing or unsupported | `unusable` |
| `UNRECONCILED_TOTAL` | `warning` or `error` | Line sum differs from invoice total beyond tolerance | `partial` for small discrepancies, `unusable` for material discrepancies |
| `LOW_CONFIDENCE_LINE` | `warning` | A monetary line is uncertain | Exclude or mark the line as uncertain |
| `UNPARSED_SECTION` | `warning` or `error` | A PDF area could not be converted into lines | Preserve unexplained amount; escalate if major |
| `DUPLICATE_LINE_CANDIDATE` | `warning` | Two extracted lines may represent the same charge | Exclude one candidate until validated |
| `CONFLICTING_METADATA` | `error` | PDF identifiers conflict with `billing-api` metadata | `unusable` |
| `UNSUPPORTED_LAYOUT` | `error` | The PDF layout cannot be parsed by the current extractor | `unusable` |
| `MISSING_LINE_EVIDENCE` | `warning` | A line has an amount but no page/text evidence | Do not use it for customer-facing proof |

Warnings can appear globally under `extraction.warnings` or locally under a line.
Line-level warnings must be promoted to global warnings when they affect
reconciliation or customer-facing certainty.

## Reconciliation Rules

Reconciliation checks whether extracted monetary lines explain the invoice total.
It must run before any invoice-to-invoice comparison.

### Fields

| Field | Type | Description |
|---|---|---|
| `status` | enum | `reconciled`, `unreconciled`, or `not_applicable` |
| `basis` | enum | `tax_included` for V1 |
| `included_line_ids` | string array | Lines included in the arithmetic sum |
| `excluded_line_ids` | string array | Lines ignored during reconciliation |
| `line_sum_tax_included_cents` | integer | Sum of included tax-included line amounts |
| `invoice_total_tax_included_cents` | integer or null | Extracted invoice total |
| `difference_cents` | integer or null | Invoice total minus included line sum |
| `tolerance_cents` | integer | Accepted rounding tolerance |
| `unexplained_amount_cents` | integer or null | Difference that remains unexplained |
| `notes` | string array | QA/debug notes not used as customer wording |

### Inclusion Rules

Include:

- subscription, option, usage, overage, one-off, prorata, discount, and adjustment
  lines;
- tax lines only when the invoice total adds tax as autonomous billable lines;
- negative lines when they represent discounts or credits that reduce the total.

Exclude:

- subtotal, total, amount due, or balance summary rows;
- previous balance and payments already received, unless the invoice total being
  reconciled explicitly includes them;
- duplicate candidates;
- low-confidence monetary lines;
- non-monetary descriptive rows;
- unparsed sections.

Every excluded monetary line must be listed in `excluded_line_ids`. If exclusion
can affect a customer explanation, it must also produce a warning.

### Formula

- `line_sum_tax_included_cents` is the sum of included line amounts.
- `difference_cents = invoice_total_tax_included_cents - line_sum_tax_included_cents`.
- `status = "reconciled"` when `abs(difference_cents) <= tolerance_cents`.
- `status = "unreconciled"` when the difference exceeds tolerance.
- `status = "not_applicable"` when the invoice total or usable lines are missing.
- `unexplained_amount_cents` equals the non-tolerated difference when unreconciled.

Initial tolerance is `1` cent. This should be revisited after validating real PDF
rounding and tax presentation.

### Materiality Rule

For V1, a discrepancy is material when it is at least `500` cents or more than
`5%` of the invoice total, whichever is smaller.

- Non-material unreconciled invoices may be `partial`.
- Material unreconciled invoices are `unusable` by default.
- Product owners may override thresholds after reviewing anonymized fixtures.

### Pairwise Comparison Rules

| Previous Invoice | Current Invoice | Comparison Decision |
|---|---|---|
| `parseable` | `parseable` | Full comparison allowed |
| `parseable` | `partial` | Compare confirmed lines only |
| `partial` | `parseable` | Compare confirmed lines only |
| `partial` | `partial` | Limited comparison; escalation recommended |
| `unusable` | any status | Comparison forbidden |
| any status | `unusable` | Comparison forbidden |

When either invoice is `partial`, the bot must say which part is confirmed and
which amount remains unexplained. `difference_cents` and
`unexplained_amount_cents` are extraction quality indicators; they must never be
presented as business causes.

## Validation Questions For Anonymized PDFs

Use the first anonymized Galaxion PDFs to validate or change this contract.

### PDF Structure

- Are invoice sections stable from month to month?
- Do PDFs contain multi-column areas, nested tables, rotated text, or repeated
  headers that affect extraction?
- Are invoice totals, taxes, previous balance, payments, and amount due clearly
  separated?
- Is there a reliable page-level text snippet for each monetary line?
- Do PDFs include enough identifiers to match `billing-api` metadata?

### Amounts And Taxes

- Are line amounts tax-included, tax-excluded, or both?
- Are VAT amounts exposed per line, per section, or only globally?
- How are tax and section subtotals rounded?
- Does the total include previous balance and payments, or only the current
  billing period?
- Are credits and discounts negative lines, section-level reductions, or separate
  summaries?

### Business Causes

- How are expired discounts represented?
- Do prorata lines expose start and end dates?
- Do option activations or deactivations appear as explicit lines?
- Do out-of-bundle lines carry volume, unit price, destination, or only amount?
- Are adjustments and commercial gestures distinguishable from discounts?
- Which causes require BSS enrichment rather than PDF-only evidence?

### Metadata And Retrieval

- Is `/bill-run-documents/{document_id}/download` always `application/pdf` for
  invoices?
- Can one account and bill period return multiple documents?
- Which identifiers are stable across PDF, `bill-run-account`, and document
  search results?
- What should happen when PDF invoice number and Galaxion metadata disagree?

### Regression Fixture Needs

- Provide two consecutive invoices for the same anonymized account.
- Include at least one simple reconciled case.
- Include at least one delta case: expired discount, prorata, out-of-bundle usage,
  option activation, or adjustment.
- Include one difficult layout or partial case if such PDFs exist in production.
- Provide the matching anonymized `bill-run-documents/search` and
  `bill-run-account` metadata for each PDF.

## Open Contract Decisions

- Confirm whether `tax_included` should remain the only reconciliation basis for
  V1.
- Confirm whether `amount_due_cents` or `total_tax_included_cents` is the correct
  customer-facing comparison total.
- Confirm whether line-level bounding boxes are required now or can remain
  optional as `bbox: null`.
- Confirm material discrepancy thresholds with billing stakeholders.
- Confirm accepted customer-facing wording for partial extraction and escalation.
