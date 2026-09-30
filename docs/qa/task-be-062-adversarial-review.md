# Adversarial Code Review — TASK-BE-062 (PDF evidence path as a selectable `BssBillingPort` adapter)

**Reviewed commit:** `b7b3b9b` on `task/TASK-BE-059-eir-b2c-period-model-and-mock`
**Date:** 2026-09-30
**Scope:** `BillRunDocumentPort`, `PdfBssBillingAdapter`, `FixtureBillRunDocumentAdapter`,
`BillingConfig` (`source=pdf` wiring), ADR-0005 amendment, tests.

## Verdict

**Proceed** — the change is architecturally clean, well-tested, and delivers the requested
selectable PDF `BssBillingPort` with a single-switch bascule and no comparison-engine change. Two
non-blocking findings (both **latent** — not triggered by current fixtures, real parser deferred)
are recorded with recommended follow-ups.

## Satisfaction Score

Score: **90/100**
QA gate: **Pass** (residual risk recorded)

## Blocking Findings

_None._

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Medium (latent) | **`PARTIAL` extraction status is dropped at the `BssBillingPort` boundary.** `PdfBssBillingAdapter.downloadAndExtract` returns the invoice for both `SUCCESS` and `PARTIAL` (via `hasInvoice()`), discarding `ExtractionResult.issues`. `ExtractionResult`'s own contract says the status is first-class "so the answer/confidence layer never treats a partial extraction as a complete one (BR-003)", but the port only carries `Invoice`/empty, so downstream sees a PARTIAL as complete. The comparison confidence gate is a *partial* safety net (a missing line usually breaks reconciliation → `residual_too_high` → escalate), but a missing zero/near-zero line can still be judged `EXPLAINABLE` at 0.9. | `PdfBssBillingAdapter` L57-65; `ExtractionResult` doc L6-9; `PdfBssBillingAdapterTest.fetchInvoice_partialExtraction_stillReturnsTheInvoice`. Does **not** trigger today: the fixture extractor only emits `PARTIAL` for a `-partial`-suffixed reference, which no fixture uses. | When the real PDFBox parser lands (deferred), either **fail-closed on `PARTIAL`** at this adapter (return empty → escalation, strict BR-003) or **thread the extraction status** to the confidence layer so a partial extraction is explicitly de-rated. Decide with Product (there is already a comparison-level `PARTIAL`/0.6 tier — extraction-PARTIAL is a different axis). |
| Low (latent) | **No extraction-outcome telemetry; a `FAILED` extraction records the BSS slice as `outcome=success`.** `telemetry.time(Slices.BSS, "pdf", …)` marks success whenever no exception is thrown, so `FAILED`/`PARTIAL` extractions are invisible as such (folded into a generic `bss success` + empty result). ADR-0005 states "extraction failures must be explicit". | `PdfBssBillingAdapter.fetchInvoice` L48-51 wraps `downloadAndExtract`; a `FAILED` result returns empty but the slice still logs `outcome=success` (observed live: `slice=bss provider=pdf outcome=success`). Consistent with `EirBssBillingAdapter` (ownership-drop also logs success). | Emit a dedicated extraction event/metric (`pdf.extraction` with `outcome=success\|partial\|failed` + issue count) so QA/Ops can measure PDF extraction quality once the real parser is live. Matters most with real PDFs; low value against fixtures. |
| Low | **No automated test for the `source=pdf` bean selection.** The `BillingConfig` switch (`mock`/`eir`/`pdf` → correct `BssBillingPort` impl) is only covered by the manual live smoke, not a unit/slice test. | `BillingConfig.bssBillingPort`; verified live (`[BILLING-BSS] source=pdf`). Consistent with `eir` (also not unit-tested). | Optional: a small `@Value`-driven config test asserting the selected adapter type per source. Consistent gap with the existing `eir` path — low priority. |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| PDF retrieval is a first-class **`BssBillingPort` implementation** (not an inline seam) | ✅ | `PdfBssBillingAdapter implements BssBillingPort`, wired in `BillingConfig` |
| Same domain `Invoice` regenerated → comparison engine unchanged | ✅ | Adapter returns `ExtractionResult.invoice()`; no change to `ComparableInvoiceService`/`BillingExplanationService`; 673 tests green incl. all billing chain tests |
| Single-switch bascule JSON ↔ PDF | ✅ | `VOICE_SUPPORT_BILLING_BSS_SOURCE ∈ {mock,eir,pdf}`; live `source=pdf` → grounded "55,47 €" identical to `mock` |
| Exercisable now without real API | ✅ | `FixtureBillRunDocumentAdapter` + fixture extractor; round-trip test |
| Fail-closed on missing/failed evidence | ✅ | empty download / `FAILED` → `Optional.empty`; `PdfBssBillingAdapterTest` (empty, failed) |
| Identity/ownership (BR-002-1) | ✅ | ownership check drops foreign-account invoice; dedicated test |
| DEC-002 (LLM never reads the PDF) | ✅ | parsing is deterministic in the adapter/extractor; LLM only formulates downstream |
| Real REST adapter appropriately deferred | ✅ | documented in ADR-0005 amend + ticket (search-response gap, OQ-003) |

## Test Evidence

- Developer tests: `PdfBssBillingAdapterTest` (6: success, partial, empty-download, failed, ownership,
  list+slice), `FixtureBillRunDocumentAdapterTest` (5: summaries, unknown account/invoice, non-empty
  PDF w/ period-id reference, end-to-end download→fixture-extractor round-trip). Backend **673** +
  ArchUnit/ContextBoundary/Naming green.
- Missing tests: `source=pdf` bean selection (non-blocking, consistent with `eir`); extraction-outcome
  telemetry (tied to the deferred real parser).
- QA scenarios to run: switch `VOICE_SUPPORT_BILLING_BSS_SOURCE=pdf` and replay the billing journeys
  (99224964 clean; 99226126/99226337 still fail-closed as with `mock`, per TASK-BE-060) — confirm parity
  with the structured path.

## Observability And Latency

- Relevant slices: **BSS** (`slice=bss provider=pdf`) — emitted for both `listInvoices` and `fetchInvoice`,
  timed, correlation-id propagated (verified live). Downstream `slice=billing outcome=explained` unchanged.
- OpenTelemetry traces / metrics / structured logs: BSS slice timer per hop → p50/p95/p99 by provider
  reportable; `provider=pdf` distinguishes the path.
- Missing: an extraction-quality event/metric distinguishing SUCCESS/PARTIAL/FAILED (non-blocking, latent —
  see finding #2). The slice-level requirement for this infra change is met.
- Risk: low. No new sensitive data on the telemetry/log path.

## Security And Privacy

- Sensitive data risk: none new. `PdfSource.content` (bytes) is never logged; the adapter logs nothing
  itself; the fixture bytes are synthetic (period id).
- Identity/access risk: **reduced** — defense-in-depth ownership check (BR-002-1) mirrors the eir adapter,
  fail-closed on account mismatch. Every port call is account-scoped.
- Logging risk: none — no account reference or invoice content in logs; only `provider=pdf` + duration.

## Required Developer Actions

_None blocking._ Recommended (before/with the real PDFBox parser + real REST `BillRunDocumentPort`):

1. Decide `PARTIAL` handling on the PDF path (fail-closed vs. thread the status to the confidence layer) —
   confirm with Product against BR-003.
2. Add an extraction-outcome event/metric (`success|partial|failed` + issue count) for PDF quality
   monitoring.
3. Optional: a config-selection test for `source=pdf`.

## Residual Risk If Accepted

- `PARTIAL` extractions are treated as complete at the `BssBillingPort` boundary (latent: never triggered
  by current fixtures; real parser deferred). Downstream reconciliation is only a partial safety net.
- PDF extraction failures are not individually observable yet (folded into `bss success` + empty). Both
  risks concentrate on the deferred real-PDF path and should be closed **before** enabling a real parser.
