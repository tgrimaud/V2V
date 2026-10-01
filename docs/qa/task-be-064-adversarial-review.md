# Adversarial code review — TASK-BE-064 (Real invoice-PDF extractor, Apache PDFBox)

- **Ticket:** TASK-BE-064 — Real `InvoicePdfExtractorPort` (`pdf.source=pdfbox`), ADR-0005 amended
- **Branch:** `task/TASK-BE-064-pdfbox-extractor`
- **Reviewer:** adversarial-code-review skill
- **Date:** 2026-10-01
- **Verdict:** ✅ Pass
- **Score:** 93/100

## Scope reviewed

- `backend/pom.xml` — Apache PDFBox 3.0.5 dependency + version property.
- `infrastructure/pdf/InvoiceTextParser.java` — deterministic text→`Invoice` parser.
- `infrastructure/adapter/out/pdf/PdfBoxInvoiceExtractorAdapter.java` — PDFBox text layer + fail-closed.
- `infrastructure/config/BillingConfig.java` — `pdf.source` switch (`fixture`|`pdfbox`), default `fixture`.
- Tests: `InvoiceTextParserTest` (7), `PdfBoxInvoiceExtractorAdapterTest` (3). Backend **708** + ArchUnit green.

## Findings

### Blocking — none

### Non-blocking / Low

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| 1 | Low | The labeled grammar (`INVOICE/ACCOUNT/PERIOD/.../LINE a\|b\|c`) is a **synthetic contract**, not the real Galaxion PDF layout; a real statement will not match without grammar tuning. | **Accepted / documented** — no anonymized sample PDF exists (OQ-003). The adapter is **off by default** (`pdf.source=fixture`); runtime behaviour unchanged. The ADR-0005 amendment + ticket Out-Of-Scope state the grammar is tuned when sample PDFs arrive. Scoping a layout parser to a non-existent sample would be guesswork. |
| 2 | Low | VAT is split at invoice level only (`tax=0` per line); line `taxExcluded==taxIncluded`. | **Accepted** — same deliberate stance as `EirBssBillingAdapter`; the PDF text grammar carries one amount per line + one global VAT, so per-line tax cannot be derived. |
| 3 | Info | `normalizeDecimal` treats the **last-occurring** separator as the decimal; a format using `.` as decimal with `,` thousands (e.g. `1,234.50`) and vice-versa are both handled, but an ambiguous `1.234` (no decimals) is read as `1.234` → 123 cents. | **Accepted** — covered by a thousands-separator test (`1 234.50`); genuinely ambiguous no-decimal grouped amounts are a layout concern folded into finding #1. |
| 4 | Info | `movePointRight(2).setScale(0, HALF_UP)` rounds sub-cent inputs; acceptable for currency cents. | No action. |

## Story coverage

- Real PDFBox text extraction + deterministic parse to domain `Invoice`. ✅ (`extract_realPdfCarryingTheGrammar_roundTripsToASuccessInvoice` writes a real PDF with PDFBox and round-trips it.)
- SUCCESS / PARTIAL / FAILED per `invoice-extraction-json.md`. ✅ (reconciled→SUCCESS; non-reconciling→PARTIAL; missing total/lines→FAILED.)
- Fail-closed on empty + corrupt, no exception, no content leak. ✅ (`extract_emptyDocument_failsClosed`, `extract_corruptBytes_failsClosedWithoutLeakingContent` asserts the raw bytes are **not** in the reason.)
- Single switch, default fixture unchanged. ✅ (`BillingConfig`.)
- Unknown category → `OTHER`; hyphenated → enum. ✅

## Test evidence

- `backend/src/test/java/.../infrastructure/pdf/InvoiceTextParserTest.java` — 7 pure-text cases.
- `backend/src/test/java/.../adapter/out/pdf/PdfBoxInvoiceExtractorAdapterTest.java` — 3 real-PDFBox cases.
- `mvn test`: **708** tests, 0 failures/errors, ArchUnit (`HexagonalArchitectureTest`, `NamingConventionsTest`, `ContextBoundaryTest`) green.
- Manual fakes only, no Mockito, GIVEN/WHEN/THEN. No `@SpringBootTest` → no DB/Ollama needed.

## Observability

- `pdfbox` is **not** the default, so no runtime slice changes. When activated, extraction runs under the existing `PdfBssBillingAdapter` BSS slice (`provider=pdf`) with a per-extraction `reason`. Not runtime-affecting by default — documented in the ticket.

## Security

- Fail-closed: no PDF content in failure reasons (only reference + error class) — asserted by test #3. No PII leak.
- The LLM never reads the PDF (DEC-002); parsing is deterministic in `InvoiceTextParser`.
- Dependency governance: PDFBox 3.0.5 is Apache-2.0, actively maintained, de-facto standard. `commons-io` verified still at 2.19.0 via `dependency:tree` (PDFBox 3.x uses its own `pdfbox-io`, no transitive downgrade).

## Required actions

- None blocking.

## Residual risk (accepted)

- Grammar does not match a real Galaxion PDF layout (finding #1) — mitigated by fixture-default + OQ-003 follow-up when sample PDFs arrive. No live path uses `pdfbox` yet.
