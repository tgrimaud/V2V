# Missing Galaxion / BSS Inputs

## Objective

This list centralizes the information to request from Galaxion, BSS, billing and
security stakeholders to validate the Voice Support Bot V1.

It avoids scattering open questions across architecture documents. Each input
must help confirm the BSS flow, adjust the invoice extraction JSON, or secure
the customer journey.

## Priority 1 - Invoice PDFs And Related Metadata

### Anonymized Invoice PDFs

Request:

- 1 or 2 anonymized Galaxion invoice PDFs;
- ideally two consecutive months for the same account;
- at least one case with a visible invoice delta;
- if possible, one simple case and one more complex case: expired discount,
  out-of-bundle usage, prorata, or option activated during the billing period.

Why:

- validate the real invoice structure;
- adjust `invoice-extraction-json.md`;
- choose or prototype the PDF extraction tool;
- create the first regression fixtures.

### `bill-run-documents/search` Responses

Request the anonymized responses associated with the provided PDFs.

Expected fields:

- `document_id`;
- `filename`;
- `contentType`;
- criteria used to find the document;
- number of documents returned for an account or billing period.

Why:

- verify how to find the correct invoice;
- confirm whether the document is always a PDF;
- reproduce the behavior in the BSS mock.

### Invoice Linkage Metadata

Request, for each PDF:

- `accountId`;
- `invoiceNumber`;
- `billPeriodId`;
- `billRunId`;
- `billRunAccountId`;
- `BillRunAccount` status;
- billing month or billing period;
- brand or customer segment if available (`brand`, `accountType`).

Why:

- validate the `bill-periods -> bill-runs -> bill-run-accounts -> documents`
  flow;
- confirm the stable identifiers to use;
- avoid basing the mock on the wrong identifier.

## Priority 2 - Reconciliation And Amounts

Request:

- how amounts are represented in Galaxion: euros, cents, decimals;
- whether PDF amounts are tax-included, tax-excluded, or both;
- how taxes are rounded;
- whether the invoice total includes previous balance, payments, or only period
  lines;
- whether discounts appear as negative lines or section reductions;
- whether credit notes, adjustments and commercial gestures are visible in the
  PDF.

Why:

- finalize reconciliation rules;
- avoid comparing amounts with different meanings;
- determine which lines must be included in or excluded from the total.

## Priority 3 - Business Causes To Confirm

Request examples or anonymized payloads to confirm:

- expired discount;
- option or service activated during the billing period;
- prorata;
- out-of-bundle data / voice / SMS;
- offer change;
- adjustment;
- one-off fee;
- tax or tax change.

For each cause, request:

- the main evidence in the PDF;
- the non-PDF BSS evidence if it exists;
- the Galaxion service that owns the information;
- the effective date;
- the expected amount;
- the customer-facing business wording accepted by billing stakeholders.

Why:

- connect line differences to business causes;
- prevent the LLM from inventing an explanation;
- build comparison-engine fixtures.

## Priority 4 - Customer Identification And Security

Request:

- how the customer is identified on the phone channel;
- how the customer is identified on the web voice journey;
- which identification level allows invoice exposure;
- which information can be spoken aloud;
- which information can be displayed on the web;
- which cases require human escalation;
- which data must be masked in logs and traces.

Why:

- resolve `OQ-001` from the product backlog;
- avoid exposing invoice data to the wrong user;
- frame the pilot mode if identity is manually provided.

## Priority 5 - BSS Errors And Edge Cases

Request:

- Galaxion standard error format;
- behavior when the account is not found;
- behavior when the invoice is not found;
- behavior when the PDF document is missing;
- behavior when multiple documents match the criteria;
- behavior when the BSS responds slowly or partially;
- timeouts and pagination limits.

Why:

- reproduce errors in the mock;
- define when the bot clarifies, retries or escalates;
- avoid generic answers when the BSS is unavailable.

## What Can Move Forward Without These Inputs

While waiting for real PDFs and payloads, the team can move forward on:

- stabilizing the `invoice-extraction-json.md` contract;
- defining expected mock fixtures for `customer-eir-001` to `customer-eir-006`;
- designing the target billing domain: `Invoice`, `InvoiceLine`,
  `InvoiceComparison`, `BillingCause`, `Evidence`;
- defining the business port `BssBillingPort` and its use cases without coding
  the real Galaxion adapter;
- preparing a `bss-mock/` service with simple static payloads;
- prototyping PDF extraction on a synthetic non-Galaxion PDF;
- preparing product acceptance scenarios for nominal, partial and unusable
  invoice cases;
- benchmarking the Pipecat/Gradium voice target independently from the BSS.

## Related Open Questions

- Which reconciliation tolerance will be acceptable after reading real PDFs?
- Can anonymized PDFs be obtained quickly, or should synthetic invoices be
  created to start?
- Is the PDF contractually considered sufficient evidence?
- Does an undocumented structured source exist for invoice lines?
- Should extracted JSON be retained for audit and regression tests?
