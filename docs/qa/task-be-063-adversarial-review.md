# TASK-BE-063 — Adversarial Code Review

**Ticket:** TASK-BE-063 — Real Galaxion `bill-run-documents` REST adapter (search + download)
**Branch:** `task/TASK-BE-063-bill-run-documents-rest`
**Reviewer:** adversarial-code-review skill
**Date:** 2026-10-01
**Scope reviewed:** `BillRunDocumentClient`, `RestBillRunDocumentAdapter`, `GalaxionBillRunDocumentAdapter`,
`BillingConfig` wiring + `BillingBssProperties`, `GalaxionBillRunDocumentAdapterTest`.

## Verdict

Proceed.

## Satisfaction Score

Score: 94/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | The thin HTTP mapping (`RestBillRunDocumentAdapter`) has no unit test. | No `MockRestServiceServer`/HTTP harness exists in the project; the sibling `RestBillingEnquiryAdapter`/`RestBillingServiceAdapter` are likewise untested. | Accept as a consistent residual. Introduce one HTTP-contract harness covering **all** Galaxion REST adapters as a separate effort (would also validate query-param building + octet-stream mapping here). |
| Low | `GalaxionBillRunDocumentAdapter` imports `GalaxionUser` from the `eir` package. | `import …bss.eir.BillingEnquiryClient.GalaxionUser` | Acceptable — it is the shared Galaxion auth concept and both live in `adapter/out/bss/*`. If a third Galaxion service lands, extract a shared `bss` auth type. |
| Info | `download` always passes `billPeriodId = null`. | `GalaxionBillRunDocumentAdapter.download` | Fine for V1 — the param is optional and `accountId + invoiceNumber` is sufficient to locate the document. Revisit only if the search returns multiple period-ambiguous documents. |
| Info | No explicit BR-002-1 ownership check inside this adapter (unlike `EirBssBillingAdapter`). | search is scoped by `accountId`; `PdfBssBillingAdapter.fromExtraction` still drops a foreign-account invoice. | Acceptable — ownership is enforced by the account-scoped search **and** by the downstream extracted-invoice ownership check (defense in depth). |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| Both routes implemented (search + download) with correct params/headers/octet-stream | Yes | `RestBillRunDocumentAdapter.search`/`download` — galaxion-user-* headers, query params for non-blank criteria, `byte[]` body, `404 → empty` |
| `download` wired search→download, fail-closed | Yes | `GalaxionBillRunDocumentAdapter.download` + tests (no doc / no bytes / zero bytes → empty) |
| `listDocuments` documented + fail-closed (search lacks period/amount) | Yes | adapter returns `List.of()` with a documented reason; test `listDocuments_isFailClosedEmpty…` |
| Selection is a single config; default unchanged (fixtures) | Yes | `BillingConfig.billRunDocumentPort` gated on `billrun.base-url`; blank → `FixtureBillRunDocumentAdapter` |
| Tests + suite green | Yes | `GalaxionBillRunDocumentAdapterTest` (6); backend **691** + ArchUnit green |

## Test Evidence

- Developer tests: `GalaxionBillRunDocumentAdapterTest` (6, manual fake of `BillRunDocumentClient`, GIVEN/WHEN/THEN,
  no Mockito): search→download round-trip + reference/bytes, no-document, empty download, zero-byte download,
  blank-id skip, `listDocuments` fail-closed. Backend suite 691 + ArchUnit (Hexagonal/ContextBoundary/Naming) green.
- Missing tests: HTTP-layer mapping of `RestBillRunDocumentAdapter` (query-param building, octet-stream, 404) — see Low finding.
- QA scenarios to run: none required at runtime (adapter is wired off by default). When a base URL is provisioned
  (OQ-003), add a live/contract smoke test against the Galaxion dev tenant.

## Observability And Latency

- Relevant slices: BSS (`provider=pdf`).
- OpenTelemetry traces: none added — **the adapter is not reachable at runtime** (base URL unset by default).
- Metrics: when activated it runs under the existing `PdfBssBillingAdapter` BSS slice (`provider=pdf`), which already
  records latency + a non-PII outcome `reason`.
- Structured logs: `BillingConfig` logs the selected document source (fixture vs real base URL) at startup, no PII.
- Missing: nothing required — **not runtime-affecting** until the base URL is set.
- Risk: low. Re-review observability when the base URL is provisioned (ensure the BSS slice records real-network outcomes).

## Security And Privacy

- Sensitive data risk: the downloaded PDF bytes are invoice PII but are never logged; carried only as `PdfSource` to the extractor.
- Identity/access risk: `galaxion-user-*` headers default to `SYSTEM` (same stance as the Eir adapters); identity→header
  derivation remains a follow-up (BR-002-1). Document reference logged is a UUID, not PII.
- Logging risk: none — startup logs the base URL + user-type only; no account/invoice content.

## Required Developer Actions

1. None blocking. (Optional) track the shared Galaxion REST HTTP-contract test harness as a separate task.

## Residual Risk If Accepted

- The real routes are **implemented but unproven against a live tenant** (OQ-003); the adapter is intentionally wired
  off by default, so no runtime behaviour changes until a base URL is set and the real PDFBox extractor lands.
- `listDocuments` stays fail-closed-empty until the `bill-run-documents/search` response carries period/amount
  (coordination request / `missing-inputs.md`).
