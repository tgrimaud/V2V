# ADR-0005: Invoice PDFs Are Extracted Before LLM Explanation

## Status

Accepted

> **Implementation status (2026-08-05): NOT IMPLEMENTED — target decision.** No
> `InvoicePdfExtractor` or extraction-status handling exists in `backend/src/main`
> yet (grep-verified). Deferred with billing V1 (Sprint 14, gated by OQ-004 for
> PDF fixtures).
>
> **Structured-source candidate (2026-09-08, OQ-003).** The BSS owner shared the
> real billing-module data model (`docs/integrations/galaxion/bss-billing-data-model.md`):
> invoices are stored as a structured `invoice → invoice_section → invoice_group →
> invoice_item` tree with amounts at every level. If reachable read-only (via
> `billing-api`), the comparison engine could consume **structured lines directly**,
> making PDF extraction the **fallback** rather than the primary evidence path. This
> does not overturn the decision (the port already anticipates it — see Consequences),
> but it may reduce the extractor to a secondary path. Deferred pending the access
> route and field semantics (OQ-003).

> **Update (2026-09-30, TASK-BE-062) — PDF path promoted to a selectable `BssBillingPort`
> adapter.** The PDF evidence path is no longer an inline "fallback seam" called from inside
> the explanation service. It is now a **first-class, selectable implementation of the same
> `BssBillingPort`** the structured JSON adapter implements, so the comparison/confidence/composer
> chain is unchanged whichever source is active. Selection is a single config switch,
> `VOICE_SUPPORT_BILLING_BSS_SOURCE` ∈ `{mock, eir, pdf}`. The `pdf` source uses
> `PdfBssBillingAdapter`, which composes a new outbound port `BillRunDocumentPort`
> (`listDocuments` + `download` → `PdfSource`, mapping Galaxion `GET /bill-run-documents/search`
> and `GET /bill-run-documents/{id}/download`) with the existing `InvoicePdfExtractorPort`
> (`PdfSource` → `ExtractionResult` → `Invoice`). The LLM still never reads the PDF (DEC-002);
> parsing is deterministic and lands in `PdfBssBillingAdapter`. Fail-closed: an empty download or a
> `FAILED` extraction → `Optional.empty` (safe escalation, never a 500), plus a defense-in-depth
> ownership check (BR-002-1). A `FixtureBillRunDocumentAdapter` (backed by the same in-memory
> invoice fixtures) makes `source=pdf` exercisable now.
>
> **Amendment (2026-10-01, TASK-BE-063 + TASK-BE-064).** Both deferred pieces are now implemented
> (wired **off by default**): (1) the real REST `BillRunDocumentPort` adapter
> (`GalaxionBillRunDocumentAdapter` over `RestBillRunDocumentAdapter`) — `download` works
> (search→download→`PdfSource`), `listDocuments` fail-closes because `bill-run-documents/search`
> still lacks period/amount (`missing-inputs.md`, OQ-003); and (2) the **real `InvoicePdfExtractorPort`**
> (`PdfBoxInvoiceExtractorAdapter`, `pdf.source=pdfbox`) using Apache PDFBox for deterministic text
> extraction + an `InvoiceTextParser` aligned with `invoice-extraction-json.md` (SUCCESS/PARTIAL/FAILED
> on reconciliation; fail-closed on empty/corrupt). A golden cross-check (`PdfFixtureEquivalenceTest`)
> proves the parser round-trips **both** fixture sets — the six synthetic journeys (`BssBillingFixtures`)
> **and** the three real accounts transcribed from the anonymized eir B2C PDFs (`EirB2cSampleFixtures`,
> `eir-b2c-invoice-samples.md`) — to the same business data.
>
> **Important scoping:** the parser reads a **synthetic labeled grammar**, not the real eir B2C PDF
> layout, and the raw anonymized PDFs are **held outside the repo** (per `eir-b2c-invoice-samples.md`), so
> the cross-check is a semantic round-trip, not proof the real eir layout is handled. Tuning the parser to
> the real eir B2C layout (header + per-service sections + negative discount lines + prorata line periods +
> invoice-level 23% VAT) and validating `parse(real eir PDF) == EirB2cSampleFixtures` is **TASK-BE-065**
> (needs the raw PDF bytes — OQ-003). Defaults stay fixture so local/pilot behaviour is unchanged.

## Context

The identified Galaxion billing path provides invoice documents through
`billing-api`, but no validated endpoint has been identified yet for structured
invoice lines.

The V1 billing assistant still needs line-level evidence to compare invoices and
explain deltas.

## Decision

Invoice PDF documents must be extracted into deterministic structured JSON before
comparison and before any LLM-generated explanation.

The `InvoicePdfExtractor` contract must produce normalized invoice data suitable
for reconciliation and comparison. The LLM may cite or explain the extracted
evidence, but it must not parse the PDF as the primary calculation mechanism.

## Consequences

- PDF extraction quality becomes a critical part of billing correctness.
- Extraction contracts must use stable numeric formats, including integer cents
  for internal calculation inputs.
- Extraction failures must be explicit and may trigger escalation.
- If a structured BSS endpoint is validated later, it can replace or complement
  PDF extraction behind the same domain port.

## Alternatives Considered

- **Let the LLM read invoice PDFs directly**: rejected because billing amounts
  and line-level evidence must be deterministic and auditable.
- **Wait for a structured invoice-line endpoint**: rejected because V1 can move
  forward with a controlled extraction contract while keeping the port
  replaceable.

## Related Documents

- `docs/product/v1-scope.md`
- `docs/integrations/galaxion/bss-integration-plan.md`
- `docs/integrations/galaxion/invoice-extraction-json.md`
