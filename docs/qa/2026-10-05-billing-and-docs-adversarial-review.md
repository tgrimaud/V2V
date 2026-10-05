# Adversarial Review — Billing subsystem + documentation (2026-10-05)

Comprehensive gate review requested after merging BUG-028, TASK-BE-066 and TASK-BE-067 into
`feat/restart-from-scratch`. Reviewed with the `adversarial-code-review` skill.

## Scope

- **Code (in depth):** the billing bounded context — deterministic comparison
  (`InvoiceComparisonService`, `ComparisonConfidenceService`), the PDF evidence path
  (`PdfBssBillingAdapter`, `SampleEirB2cBillRunDocumentAdapter`, `EirB2cInvoiceLayoutParser`,
  `EirInvoiceBodyReader`, `EirInvoiceText`), explanation (`BillingExplanationComposer`,
  `BillingExplanationService`), wiring (`BillingConfig`), fixtures and the real-PDF resources.
- **Documentation (in depth):** backlog ledgers (`backlog-index.md`, `tasks/*`, `bugs/*`,
  `done-tasks.md`), ADRs touched (ADR-0003/0005), QA review artifacts, the English-only rule and the
  anonymization guarantee for committed sample data.
- **Not re-reviewed here (unchanged this session):** the Python voice runtime (`voice-agent/`), the
  conversation/answer-engine module, deploy/Ansible, and the frontend. Flagged only if impacted.

## Verdict

Proceed. The billing subsystem is coherent, deterministic, fail-closed and well-tested; documentation
is accurate after two stale post-merge statuses were corrected during this review.

## Satisfaction Score

Score: 92/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Medium → **fixed in this review** | Stale post-merge status: `TASK-DOC-010` still read "In progress" in `backlog-index.md` and `tasks/doc-tasks.md` though merged (`ba33705`). Exactly the "stale status after a fast-forward/no-ff merge" trap. | `backlog-index.md` L128; `doc-tasks.md` | Fixed → `✅ Merged (ba33705)` in both the registry row, the task table and the task block. |
| Low | Committed sample data (`EirB2cSampleFixtures`, the 6 `*_EIR_MOBILE_TEST_*_B2C.pdf`) carries MSISDN/account tokens (`085 7092782`, `076-1089762`, `99224964`…) that are also embedded in `Evidence` labels and can reach the LLM context on the ADR-0052 D1a path. | fixtures L58–157; `eir-b2c-invoice-samples.md` "real **anonymized**" | Documented as anonymized → acceptable. Keep the guarantee: never commit non-anonymized samples; the composer only voices computed amounts (not raw labels), so no number is spoken. |
| Low | `SERVICE_ADDED`/`SERVICE_REMOVED` infer a new/removed service purely from a SUBSCRIPTION line appearing/disappearing; a plan **swap** reads as remove+add rather than a single "plan change". | `InvoiceComparisonService.cause` | Accepted (TASK-BE-067 residual); residual still reconciles to €0. Revisit if plan-swap wording is wanted. |
| Low | Line match key is the label-derived slug `code`; stable for current eir labels but a product rename across months would read as DISAPPEARED+APPEARED (still fully attributed, €0 residual). | `EirInvoiceBodyReader.uniqueCode` | Accepted (BUG-028 residual). Revisit when a stable product id is available in the PDF. |
| Info | `EirInvoiceBodyReader.Header.missing()` uses brace-less single-line `if` statements. | `EirInvoiceBodyReader` L101–105 | Minor code-guidelines deviation (pre-existing); add braces on next touch. |
| Info | `BillingConfig` imports are not strictly grouped/ordered (billrun imports interleaved). | `BillingConfig` L26–30 | Cosmetic; ArchUnit is green. |
| Info | `SampleEirB2cBillRunDocumentAdapter.resourceName` does `invoiceId.value().substring(0,6)`; safe only because `knownInvoice()` gates it to 16-digit catalog ids. | adapter L73–76 | Fine; the guard makes a short id unreachable. Keep the ordering (guard before substring). |

## Story Coverage

| Ticket | Acceptance | Covered? | Evidence |
|---|---|---|---|
| BUG-028 | same-category lines no longer collapsed; 99224964 residual €0 | Yes | `EirB2cBillingComparisonE2eTest`, `InvoiceComparisonServiceTest.never_drops…`, `EirInvoiceTextTest` |
| TASK-BE-066 | runtime parses real PDF bytes end to end; default stays fixture | Yes | `SampleEirB2cBillRunDocumentAdapterTest`, `EirB2cBillingComparisonE2eTest`, `BillingConfig` switch |
| TASK-BE-067 | new/removed service → named cause; opaque change stays UNEXPLAINED | Yes | comparison + confidence + composer tests; E2E 99226126/99226337 residual €0 |

## Test Evidence

- Full backend suite **715** + ArchUnit (`HexagonalArchitectureTest`, `ContextBoundaryTest`,
  `NamingConventionsTest`) green. BDD `RunKnowledgeBddTest` (41) green.
- Billing coverage spans domain units (comparison, confidence, composer, intent, identity), adapter
  tests (PDF chain, sample document source, fixture), and a real-PDF end-to-end comparison over all
  three sample accounts. No Mockito; manual fakes; GIVEN/WHEN/THEN.
- Gap: no `SERVICE_REMOVED` case in the real-PDF E2E (no sample account drops a service) — covered by a
  domain unit test instead, which is the right level.

## Observability And Latency

- `PdfBssBillingAdapter` records the BSS slice with non-PII `reason`
  (`document_unavailable | extraction_failed | extraction_partial | ownership_mismatch`) and success,
  enabling per-outcome PDF-quality measurement.
- Comparison/confidence/composer run inside the already-instrumented billing routing path (ADR-0052); no
  new runtime slice is introduced by BUG-028/BE-066/BE-067, so no new spans/metrics are required.
- No PII in telemetry; account/MSISDN never logged by the changed code (BillingConfig logs base URLs +
  source only). Residual now lower for multi-service accounts → fewer false low-confidence escalations.

## Security And Privacy

- Sensitive data: committed sample data is documented anonymized (Low finding above). Telemetry reasons
  are non-PII. The LLM is amount-grounded (DEC-002) and only restates computed amounts.
- Fail-closed holds: empty download, FAILED **and** PARTIAL extraction, and an account/ownership
  mismatch all yield `Optional.empty` (BR-002-1/BR-003). PARTIAL-as-fail-closed is correct (a partial
  parse must never look complete).
- Read-only BSS; no write path. No secrets committed (checked: no tokens/passwords in the changed set).

## Maintainability

- All changed classes are within the size budgets (`InvoiceComparisonService` 185,
  `EirInvoiceBodyReader` 192, `BillingExplanationComposer` 121 lines); methods small and single-purpose.
- Strong rationale comments tie code to ADRs/BRs/tickets. The three BSS sources and three PDF sources sit
  behind ports with a single config switch each — provider-replaceable per the product rule.

## Required Developer Actions

1. None blocking. (Stale-status finding already fixed in this review.)
2. Keep the anonymization guarantee for any future committed sample invoice.

## Residual Risk If Accepted

- Plan-swap voiced as remove+add; product rename → appeared/disappeared (both still reconcile to €0).
- An opaque in-place subscription price change stays `UNEXPLAINED` and escalates — intended (BR-003).
