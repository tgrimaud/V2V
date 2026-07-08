# BSS V1 Integration Plan

## Objective

This document prepares the integration of the Voice Support Bot with the
operator's existing BSS.

The target BSS is composed of several microservices. To move quickly without
waiting for all final accesses, V1 must start with a contract-compatible BSS
mock: it exposes the same useful APIs as the target BSS microservices, with
realistic anonymized fixtures.

## Architecture Principle

The Java backend must not consume bot-specific internal fixtures directly. It
must consume a stable BSS contract through an adapter.

```text
Voice Support Backend
        |
        | domain port: BillingContextPort / BssCustomerContextPort
        v
BSS adapter
        |
        +--> local BSS mock, API-compatible
        |
        +--> BSS sandbox / real BSS, same useful contract
```

The mock must be replaceable by configuration: URL, authentication and
environment profile. The invoice comparison domain must not change when moving
from the mock to the real BSS.

## Identified BSS Microservices

| V1 Need | Source Microservice | Priority | Notes |
|---------|---------------------|----------|-------|
| Identify / search for a customer | `contacts-service` + `accounts-service` | Medium | Can be simplified at first if the channel already provides the customer |
| List invoices / periods | `billing-api` | High | `billing-service` is no longer used |
| Retrieve an invoice / invoice document | `billing-api` | High | Use `bill-run-documents/search` with one or more criteria |
| Retrieve a detailed structured invoice | Invoice PDF + `InvoicePdfExtractor` | High | No structured endpoint identified for invoice lines |
| Retrieve invoice lines | Invoice PDF + `InvoicePdfExtractor` | High | Extract and normalize lines from the PDF |
| Retrieve discounts / options / contract | `accounts-service`, `contracts-service`, `addons-service`, `discounts-service` | High | Needed to explain discount expiration, option, offer, subscription |
| Retrieve out-of-bundle usage | `cdr-usage-consumption-service` or `usages-service` | Medium | Needed to explain usage causes |
| Retrieve billing events | `customer-history-service`, `events-store-service`, `change-offers-service`, `adjustments-service` | High | Option activation, offer change, adjustment, proration |

## Provided Galaxion Catalog

The target BSS is called Galaxion. The Swagger entries below are the starting
points to analyze when implementation of the API-compatible mock begins.

| Microservice | Swagger |
|--------------|---------|
| `account-receivable-service` | `https://accounts-receivable-service-v2.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `account-receivable-facade` | `https://account-receivable-facade.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `accounts-service` | `https://accounts-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `acquisition-prospects-service` | `https://acquisition-prospects-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `addons-service` | `https://addons-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `addresses-service` | `https://addresses-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `adjustments-service` | `https://adjustments-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `appointments-service` | `https://appointments-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `barrings-service` | `https://barrings-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `billing-cycles-service` | `https://billing-cycles-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `billing-service` | `https://billing-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `billing-api` | `https://billing-api.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `carts-service` | `https://carts-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `catalog-service` | `https://catalog-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `cdr-usage-consumption-service` | `https://cdr-usage-consumption-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `change-offers-service` | `https://change-offers-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `collections-service` | `https://collections-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `contract-builder-service` | `https://contract-builder-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `contacts-service` | `https://contacts-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `contracts-service` | `https://contracts-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `credit-limits-service` | `https://credit-limits-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `credit-scores-service` | `https://credit-scores-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `cross-sell-service` | `https://cross-sell-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `customer-history-service` | `https://customer-history-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `deposits-service` | `https://deposits-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `discounts-service` | `https://discounts-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `documents-service` | `https://documents-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `email-sender-service` | `https://email-sender-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `equipments-service` | `https://equipments-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `events-store-service` | `https://events-store-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `iam-facade` | `https://iam-facade.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `notifications-service` | `https://notifications-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `number-swaps-service` | `https://number-swaps-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `otp-verification-service` | `https://otp-verification-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `payments-service` | `https://payments-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `sales-service` | `https://sales-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `search-engine-service` | `https://search-engine-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `search-models-service` | `https://search-models-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `security-questions-service` | `https://security-questions-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `sms-sender-service` | `https://sms-sender-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `top-ups-service` | `https://top-ups-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `unique-references-service` | `https://unique-references-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `usages-service` | `https://usages-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |
| `users-service` | `https://users-service.rke-itsf-devgalaxioncore-prd.itsf.io/swagger-ui/index.html` |

## V1 Swagger Shortlist

To avoid spreading the analysis too widely, the first Swagger entries to open
are:

| Order | Microservice | Why |
|-------|--------------|-----|
| 1 | `billing-api` | Target source for periods, bill runs, invoice document search and download. Initial analysis: [`galaxion-billing-contracts.md`](galaxion-billing-contracts.md) |
| 2 | `accounts-service` | Link customer, account, subscription and commercial context |
| 3 | `contracts-service` | Retrieve the active contract, offer and subscription for the compared periods |
| 4 | `discounts-service` | Identify discounts, validity and expiration |
| 5 | `addons-service` | Identify billed options and services |
| 6 | `cdr-usage-consumption-service` | Explain out-of-bundle usage and detailed consumption |
| 7 | `customer-history-service` | Retrieve business events useful for the explanation |
| 8 | `events-store-service` | Check whether it contains missing technical/business events |
| 9 | `change-offers-service` | Explain offer changes |
| 10 | `adjustments-service` | Explain adjustments, corrections and gestures |
| 11 | `contacts-service` | Identify or confirm the customer if the channel is not enough |

## Swagger Analysis Order

### 1. Billing

First Swagger to analyze.

Questions to answer:

- How are invoices or periods listed for a customer?
- How is the latest invoice and the previous period identified?
- How is an invoice document retrieved through `bill-run-documents/search`?
- How are the invoice total, currency, period dates and status retrieved?
- How are lines, taxes, one-off fees, adjustments and proratas extracted from
  the invoice PDF?
- Which error codes exist for invoice not found, customer not found, forbidden
  access and unavailable data?

Expected endpoints to locate:

- list invoices by customer/account;
- search invoice document;
- download invoice document;
- extract invoice lines from PDF;
- get billing periods, if distinct from invoices.

### 2. Account

Second Swagger to analyze.

Questions to answer:

- How is the active contract retrieved for a given period?
- How are active offers, options and services retrieved?
- How are discounts and their validity dates retrieved?
- How are change events retrieved: option activation, offer change,
  cancellation, expired discount, commercial gesture?
- Are proratas and adjustments carried by `account`, `billing`, or both?

Expected endpoints to locate:

- get account / subscription;
- get active offers and options;
- get discounts;
- get account events / lifecycle events.

### 3. CDR

Third Swagger to analyze.

Questions to answer:

- How is usage retrieved for a billing period?
- How are included, out-of-bundle, roaming, data, voice and SMS usage
  distinguished?
- Are out-of-bundle amounts present in CDR or only in `billing`?
- How is a CDR usage item linked to an invoice line?

Expected endpoints to locate:

- get usage by customer/account and period;
- get out-of-bundle usage;
- get usage detail by type.

### 4. Contact

Fourth Swagger to analyze.

Questions to answer:

- How is a customer searched or confirmed from the phone or web channel?
- Which identifier links `contact` to `account`?
- Which fields can be exposed orally or on the web?
- Which cases require clarification or escalation?

Expected endpoints to locate:

- search contact;
- get contact detail;
- get accounts for contact.

## Minimum V1 Mock Contract

The mock must cover at least four journeys.

### Nominal Journey

- Customer identified.
- Two comparable invoices.
- Global delta reconciled with explainable causes.
- Evidence available for each main cause.

### Expired Discount

- Previous invoice with active discount.
- Current invoice without the discount.
- Event or validity period confirming the expiration.

### Out-Of-Bundle Usage

- Current invoice with an out-of-bundle line.
- CDR showing the associated usage.
- Cause linked to the invoice line and to the usage.

### Proration / Option

- Option activated during the period.
- Invoice line with prorated amount.
- Account event confirming the activation date.

### Insufficient Data

- An invoice or an evidence item is missing.
- The bot must explain the limitation and must not invent the cause.

### Unreliable PDF Extraction

- The PDF is downloaded but some lines are not parsed reliably.
- The bot must state that the analysis is incomplete and must not present
  uncertain amounts as confirmed.

## Recommended Fixtures

| Fixture | Objective |
|---------|-----------|
| `customer-eir-001` | Nominal case with a more expensive current invoice |
| `customer-eir-002` | Expired discount only |
| `customer-eir-003` | Data overage with CDR evidence |
| `customer-eir-004` | Option activated mid-period with proration |
| `customer-eir-005` | Incomplete BSS data |
| `customer-eir-006` | Invoice PDF with partial or ambiguous extraction |

The data must be anonymized and remain realistic: EUR amounts, monthly periods,
plausible telecom offers, consistent dates and deltas that reconcile with the
stated causes.

## Errors To Reproduce

The mock must reproduce errors that are useful for product behavior:

- customer not found;
- account not found;
- invoice not found;
- period unavailable;
- forbidden access;
- BSS service unavailable;
- timeout;
- partial data;
- inconsistent data.
- invoice PDF not found;
- invoice PDF not parseable.

Each error must use the same format as the target BSS once that format is known.

## Information To Request When Swaggers Are Available

The living list of missing inputs is maintained in
[`missing-inputs.md`](missing-inputs.md). It must be updated after every BSS,
PDF or security feedback loop.

For each microservice, extract:

- base path;
- useful V1 endpoints;
- HTTP method;
- required parameters;
- identifiers used (`contactId`, `accountId`, `customerId`, `invoiceId`, etc.);
- response schema;
- error schema;
- authentication;
- required headers: correlation id, tenant, channel, locale;
- pagination;
- date, currency and timezone conventions.
- format and type of returned invoice documents.

## Open Decisions

- Do invoice lines really come from `billing`?
- Are proratas explicit in `billing` or inferred through `account`?
- Are adjustments invoice lines, account events, or both?
- Should the backend call BSS microservices directly, or go through an existing
  operator BSS facade?
- Should the mock be a dedicated service in `docker-compose` or a Java backend
  profile?
- Which PDF extraction tool provides the best reliability on Galaxion invoices?
- Should extracted JSON be stored for audit and regression tests?

## Implementation Recommendation

Start with a separate fake BSS server in `docker-compose`, exposed on a dedicated
port, with versioned JSON fixtures.

Benefits:

- the backend consumes real HTTP APIs as it will with the BSS sandbox;
- contracts can be tested by endpoint;
- fixtures remain readable by Product, BSS and QA;
- moving from mock to sandbox is done by URL and authentication configuration.

Recommended implementation:

- `bss-mock/` for the fake server and fixtures;
- endpoints aligned with the real Swagger contracts as soon as they are
  available;
- expected PDF and extraction JSON fixtures, aligned with
  [`invoice-extraction-json.md`](invoice-extraction-json.md);
- contract tests on useful V1 payloads;
- backend configuration `BSS_BASE_URL` or equivalent;
- local `bss-mock` profile in `docker-compose`.
