# Missing Galaxion / BSS Inputs For Invoice Comparison

## Objective

This document lists the inputs needed from the Galaxion / BSS team before
implementing invoice comparison in the Voice Support Bot V1.

The goal is to avoid building the comparison engine on assumptions. The current
working direction is to use `billing-api` as the billing source, retrieve invoice
documents through the bill-run document flow, extract invoice PDFs into
deterministic JSON, and compare only validated structured data. The LLM must not
read PDFs directly to calculate amounts or infer billing causes.

## Scope

The requested inputs must let the team validate:

- how to find the right invoices for a customer and billing period;
- how invoice PDFs and Galaxion metadata are linked;
- whether any structured invoice-line source exists in addition to the PDF;
- how extracted amounts should reconcile with BSS totals;
- which BSS evidence confirms the business cause of a billing delta;
- which errors, permissions and edge cases must be reproduced in the mock.

## Priority 1 - Blocking Inputs

These inputs are required before implementing the real comparison behavior.

### Anonymized Invoice Pairs

Request at least three anonymized invoice pairs for the same account across two
consecutive billing periods.

Required examples:

- one nominal case where the two invoices compare cleanly;
- one invoice increase caused by an expired discount, option activation, offer
  change, prorata, out-of-bundle usage, adjustment, or one-off fee;
- one partial or problematic case where the PDF, metadata, or supporting BSS
  evidence is incomplete.

For each invoice pair, request:

- the customer-facing invoice PDFs;
- the expected business explanation from the billing team;
- the expected total delta in cents;
- the amount that should remain unexplained, if any;
- any data that must be masked before storing the sample as a fixture.

Why this is blocking:

- the PDF structure drives `InvoicePdfExtractor`;
- the comparison engine needs realistic line labels, totals, taxes and periods;
- regression fixtures must reflect real Galaxion invoices, not synthetic guesses.

### Billing Document Retrieval Contract

Request the exact `billing-api` flow and anonymized payloads used to retrieve the
PDFs.

Required payloads:

- `GET /bill-periods?year={year}`;
- `GET /bill-periods/{bill_period_id}`;
- `GET /bill-runs/{bill_run_id}/bill-run-accounts/search`;
- `GET /bill-run-documents/search`;
- `GET /bill-run-documents/{document_id}/download` response metadata.

Required fields to confirm:

- `accountId`;
- `billPeriodId`;
- `billRunId`;
- `billRunAccountId`;
- `invoiceNumber`;
- bill-run account `status`;
- document `id`;
- document `filename`;
- document `contentType`;
- pagination fields and default page size;
- headers required for tenant, channel, locale, correlation and authorization.

Why this is blocking:

- the bot must retrieve the two comparable invoices deterministically;
- the mock must reproduce the useful `billing-api` behavior;
- comparison should fail closed when an invoice cannot be uniquely identified.

### Structured Invoice Data Availability

Ask the BSS team to confirm whether any supported endpoint exposes structured
invoice sections, lines, taxes, balances or itemized amounts for the customer
invoice.

Inputs to request:

- confirmation that `billing-api` is the only V1 billing source;
- confirmation that `billing-service` must not be used for V1;
- whether `/invoices/selected` is valid for customer invoice details;
- whether `/invoices/composed` can be used for comparison or is out of scope;
- sample payloads for any endpoint considered a source of structured invoice
  lines;
- ownership and stability level of each candidate endpoint.

Why this is blocking:

- if a reliable structured source exists, it should reduce PDF extraction risk;
- if no structured source exists, the PDF extraction JSON becomes the primary
  calculation contract;
- the implementation must not depend on an undocumented endpoint without BSS
  approval.

### Amount, Currency And Tax Semantics

Request the official amount rules used by Galaxion invoices.

Required confirmations:

- whether monetary values are represented as euros, cents or decimals in each
  relevant endpoint;
- whether PDF line amounts are tax-included, tax-excluded, or both;
- whether invoice totals include previous balance, unpaid amounts, payments,
  credits or only the current billing period;
- how VAT and other taxes are rounded;
- how discounts are represented: negative lines, section-level reductions, or
  separate adjustment records;
- how credit notes, adjustments and commercial gestures appear in the PDF and
  BSS payloads;
- acceptable reconciliation tolerance between extracted lines and invoice total.

Why this is blocking:

- the comparison engine must compare amounts with the same meaning;
- internal calculation inputs should use integer cents;
- the bot must not explain a delta caused by balance carry-over as a period
  billing change.

## Priority 2 - Cause Evidence Inputs

These inputs are required to explain why one invoice differs from another without
inventing causes.

### Discount And Promotion Evidence

Request payloads and rules that show:

- active discounts on each compared period;
- discount start and end dates;
- discount amount or percentage;
- offer or subscription to which the discount applies;
- how an expired discount appears in invoice lines;
- accepted customer-facing wording for an expired discount explanation.

Candidate services to validate:

- `discounts-service`;
- `contracts-service`;
- `accounts-service`;
- `customer-history-service`.

### Offer, Option And Prorata Evidence

Request payloads and rules that show:

- offer changes;
- option or add-on activation and cancellation dates;
- service effective periods;
- prorata formula or BSS-calculated prorata amount;
- mapping between the event and the invoice line;
- accepted wording for prorata and option explanations.

Candidate services to validate:

- `contracts-service`;
- `addons-service`;
- `change-offers-service`;
- `customer-history-service`;
- `events-store-service`.

### Out-Of-Bundle Usage Evidence

Request payloads and rules that show:

- usage period covered by the invoice;
- included allowance and consumed quantity;
- out-of-bundle quantity;
- unit price or final billed amount;
- usage category: data, voice, SMS, roaming or another type;
- mapping between usage records and invoice lines.

Candidate services to validate:

- `cdr-usage-consumption-service`;
- `usages-service`;
- `billing-api`.

### Adjustments And One-Off Fees

Request payloads and rules that show:

- adjustment type;
- adjustment creation and effective dates;
- billed amount;
- tax treatment;
- relation to invoice number or billing period;
- customer-facing reason text, when available;
- escalation rule when the adjustment cannot be explained automatically.

Candidate services to validate:

- `adjustments-service`;
- `account-receivable-service`;
- `customer-history-service`;
- `events-store-service`.

## Priority 3 - Operational And Security Inputs

These inputs define how the comparison feature behaves safely in production-like
flows.

### Customer Identification And Authorization

Request:

- the identifier provided by each channel before invoice retrieval;
- how phone and web journeys map a caller or user to `accountId`;
- the minimum authentication level needed to expose invoice amounts;
- fields that may be spoken aloud;
- fields that may be displayed in the web interface;
- fields that must be masked in logs, traces and fixtures;
- cases where the bot must escalate instead of continuing.

### Error And Edge-Case Contract

Request the standard Galaxion error format and examples for:

- account not found;
- invoice not found;
- period not available;
- document not found;
- multiple matching documents;
- access forbidden;
- expired or missing token;
- BSS timeout;
- partial BSS response;
- inconsistent invoice metadata;
- non-PDF or corrupted document;
- unparseable PDF.

For each error, request:

- HTTP status;
- response body;
- stable error code;
- retryability;
- whether the bot should clarify, retry, say the analysis is unavailable, or
  escalate to a human.

### Non-Functional Inputs

Request:

- sandbox base URLs and network access requirements;
- authentication mechanism and token lifetime;
- rate limits;
- timeout recommendations;
- pagination limits;
- expected latency for billing document search and download;
- correlation-id propagation rules;
- audit requirements for extracted JSON and comparison results;
- retention policy for PDFs, extracted JSON and anonymized fixtures.

## Mock Fixture Requirements

The BSS mock should not be implemented until the BSS team validates the minimum
shape of the contracts above.

The first fixture set should cover:

- `customer-eir-001`: nominal invoice comparison;
- `customer-eir-002`: expired discount;
- `customer-eir-003`: out-of-bundle usage;
- `customer-eir-004`: option activation with prorata;
- `customer-eir-005`: incomplete BSS evidence;
- `customer-eir-006`: partial or ambiguous PDF extraction.

Each fixture should include:

- `billing-api` request and response payloads;
- invoice PDFs or anonymized PDF-like fixtures;
- expected extracted invoice JSON;
- expected comparison result;
- expected customer-facing explanation;
- expected failure or escalation behavior when data is missing.

## What Can Move Forward Without These Inputs

The team can proceed with low-risk preparation work while waiting for BSS inputs:

- define the domain vocabulary for `Invoice`, `InvoiceLine`,
  `InvoiceComparison`, `BillingCause` and `Evidence`;
- keep the `InvoicePdfExtractor` contract draft aligned with
  `invoice-extraction-json.md`;
- prepare the adapter boundary for a read-only `BssBillingPort`;
- design the mock service structure without final payload fields;
- write acceptance scenarios that explicitly mark BSS data as pending;
- benchmark PDF extraction tooling on synthetic non-Galaxion documents.

The team should not implement final comparison rules, customer-facing cause
wording, or production BSS adapters until the Priority 1 inputs are validated.

## Related Open Questions

- Is `billing-api` the only approved V1 source for invoice retrieval?
- Does a supported structured invoice-line endpoint exist, or is PDF extraction
  mandatory for all detailed comparison?
- Which identifier is the stable join key across invoice document, bill run
  account, customer account and supporting cause evidence?
- What reconciliation tolerance is acceptable on real Galaxion PDFs?
- Which BSS service is the source of truth for discounts, options, proratas,
  usage overage and adjustments?
- Can extracted invoice JSON be stored for audit and regression tests?
- Which invoice details can be exposed in voice mode after customer
  identification?
