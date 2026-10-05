# Adversarial Code Review — TASK-BE-066 (serve the real eir B2C sample PDFs at runtime)

- **Scope:** `SampleEirB2cBillRunDocumentAdapter` (new `BillRunDocumentPort`), the 6 sample PDFs
  promoted to `backend/src/main/resources/billing/eir-b2c/`, the `billrun.source` switch
  (`BillingBssProperties` + `BillingConfig.billRunDocumentPort`), and `SampleEirB2cBillRunDocumentAdapterTest`.
- **Verdict:** Pass
- **Score:** 93/100
- **Reviewer:** adversarial-code-review skill (self-review), 2026-10-05
- **Branch:** `task/TASK-BE-066-runtime-real-eir-b2c-pdf-source`

## Blocking findings

None.

## Non-blocking / Low findings

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| 1 | Low | `resourceName()` derives the file from `invoiceId.value().substring(0, 6)` — a sub-6-char id would throw `StringIndexOutOfBoundsException`. | Guarded: `download()` only calls it after `knownInvoice()`, so the id is always a catalog bill number (16 digits). Accepted; the catalog is the trust boundary. |
| 2 | Low | `listDocuments` metadata (id/period/total) comes from `EirB2cSampleFixtures`, not from parsing the PDFs or a real search. | By design (OQ-003: `bill-run-documents/search` lacks period/amount). The **compared** invoices are the real-parsed ones; the catalog is only the search stand-in. Documented in the adapter header + ADR-0005. |
| 3 | Low | The file-name date mapping relies on the eir bill-number encoding (leading `YYMMDD`). A future sample whose id does not encode the date would resolve to a missing resource. | Fail-closed (missing resource → `Optional.empty()` → `document_unavailable`), never a crash. Covered by the unknown-invoice test. |
| 4 | Info | The adapter emits no telemetry of its own. | Intentional: `PdfBssBillingAdapter` already times the BSS slice and records `document_unavailable` / `extraction_*` / `ownership_mismatch` outcomes, so download/extract failures are observable without a redundant span. |

## Story coverage

- Real PDF bytes served at runtime (not the synthetic stub): ✅ `download` returns `%PDF` content > 1 KB.
- Full runtime chain on real documents: ✅ `PdfBssBillingAdapter` + sample docs + `eir-b2c` extractor
  regenerates all 3 accounts × 2 invoices (id + account + TTC) in the test.
- Opt-in, default unchanged: ✅ `billrun.source` defaults to `fixture`; `pdf.source` defaults to `fixture`.
- Fail-closed: ✅ unknown account / unknown invoice / missing resource → `Optional.empty()`.

## Test evidence

- `SampleEirB2cBillRunDocumentAdapterTest` (4 tests): catalog listing, real `%PDF` bytes, fail-closed
  branches, and the end-to-end `PdfBssBillingAdapter` chain over all samples.
- `EirB2cRealPdfParsingTest` still green after the resource move (main resources on the test classpath).
- Backend suite: **715** tests, 0 failures/errors; ArchUnit green (new class ends in `Adapter`, lives in
  `adapter.out.bss.pdf`).

## Observability

BSS slice timing + non-PII outcome reasons (`document_unavailable`, `extraction_failed`,
`extraction_partial`, `ownership_mismatch`) are recorded by `PdfBssBillingAdapter`; config logs the
selected document source. No new runtime slice required.

## Security

- Serves only the bundled **anonymized** sample PDFs (fake names, `TEST` filenames, test IBAN); no secrets.
- No PDF content in failure reasons (inherited from `PdfBssBillingAdapter` + `PdfBoxInvoiceExtractorAdapter`).

## Required actions

None (score ≥ 90).

## Residual risk (accepted)

- `listDocuments` metadata and the file-name date mapping are tuned to the fixed eir B2C sample set
  (3 accounts × Aug/Sep 2026). Real Galaxion `search` metadata and non-eir layouts remain follow-ups
  (OQ-003), as does flipping the runtime default away from `fixture`.
