# Adversarial code review — TASK-BE-065 (Real eir B2C invoice-PDF layout parser)

- **Ticket:** TASK-BE-065 — `EirB2cInvoiceLayoutParser` (`pdf.source=eir-b2c`), follow-up of TASK-BE-064
- **Branch:** `task/TASK-BE-065-eir-b2c-layout-parser` (off `task/TASK-BE-064-pdfbox-extractor`)
- **Reviewer:** adversarial-code-review skill
- **Date:** 2026-10-01
- **Verdict:** ✅ Pass
- **Score:** 93/100

## Scope reviewed

- `infrastructure/pdf/PdfTextInvoiceParser.java` — parser seam on the shared PDFBox text layer.
- `infrastructure/pdf/EirB2cInvoiceLayoutParser.java` — header parse + assemble + reconcile.
- `infrastructure/pdf/EirInvoiceBodyReader.java` — section→group→item state machine + category inference.
- `infrastructure/pdf/EirInvoiceText.java` — date/amount/period/VAT helpers.
- `infrastructure/pdf/InvoiceTextParser.java` — now implements the seam (no behaviour change).
- `adapter/out/pdf/PdfBoxInvoiceExtractorAdapter.java` — parser-injecting constructor (default unchanged).
- `infrastructure/config/BillingConfig.java` — `pdf.source=eir-b2c` wiring.
- Test resources: 6 anonymized eir B2C PDFs; `EirB2cRealPdfParsingTest`.

## Findings

### Blocking — none

### Non-blocking / Low

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| 1 | Low | Category SUBSCRIPTION-vs-OPTION is a positional heuristic ("first recurring line = SUBSCRIPTION, rest = OPTION"), not read from the PDF. | **Accepted** — verified it reproduces **every** fixture category across all 6 real invoices; DISCOUNT/ONE_OFF/PRORATA are deterministic from sign/group/"from…until". The PDF carries no catalogue code, so category is necessarily inferred. |
| 2 | Low | Body parsing stops at the first `VAT Rate`/`Page`/`-- n of m --` and assumes the detail body is contiguous after a single "Detail of your eir service"; a 3rd-page body split would need more work. | **Accepted** — matches all six real samples (2-page invoices, body on page 2). Documented; revisit if a longer invoice appears. |
| 3 | Low | Per-line VAT is derived at a hard-coded 23% (G1), mirroring `EirB2cSampleFixtures.amount23`. | **Accepted** — the eir B2C PDF exposes VAT only at invoice level (documented G1); 23% is the Irish rate on these samples. If a non-23% invoice appears, lift to the invoice VAT-block rate. |
| 4 | Info | Exact label wording and synthetic ids/codes/evidence-source are not asserted in the validation. | **By design** — those are not in the PDF (ids/codes) or were paraphrased by the fixtures (labels); the parser keeps verbatim PDF text. Structure + amounts + categories + periods are asserted. |

## Story coverage

- Real eir layout parsed from the **actual** anonymized PDFs → domain `Invoice`. ✅
- `parse(real eir PDF) == EirB2cSampleFixtures` on identity, period windows, section→group→item tree, category,
  prorata line periods, per-line + rolled-up amounts (23% VAT split), SUCCESS/reconciliation. ✅ (6 invoices,
  3 accounts × 2 months, incl. multi-section, negative discounts, proratas, one-time groups.)
- Single switch `pdf.source=eir-b2c`; default fixture unchanged; TASK-BE-064 `pdfbox` behaviour unchanged
  (adapter default constructor). ✅

## Test evidence

- `EirB2cRealPdfParsingTest` — reads the 6 committed PDFs, parses via `EirB2cInvoiceLayoutParser`, asserts
  full structural equivalence to `EirB2cSampleFixtures`.
- `mvn test`: **711** tests, 0 failures/errors, ArchUnit green. Manual fakes, no Mockito, no `@SpringBootTest`.

## Observability

- `eir-b2c` is not the default, so no runtime slice changes. When active, extraction runs under the existing
  `PdfBssBillingAdapter` BSS slice (`provider=pdf`) + per-extraction `reason`. Not runtime-affecting by default.

## Security

- Fail-closed: FAILED on empty/missing header/no lines; PARTIAL on non-reconciliation; failure reasons carry
  only the document reference + counts, never PDF content.
- The committed PDFs are the **anonymized** eir test invoices (fake names/addresses/IBAN, "TEST" in the name);
  authorized for commit by the repo owner. The LLM never reads the PDF (DEC-002).

## Required actions

- None blocking.

## Residual risk (accepted)

- Category heuristic + 23% VAT + single-body-page assumptions (findings #1–#3) are tuned to the current eir B2C
  samples; a materially different eir layout would need extension. No non-eir layout is in scope.
