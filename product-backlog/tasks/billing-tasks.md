# Billing V1 Tasks (Sprint 14)

Ticket details for Sprint 14 — Billing Identity + BSS/PDF Evidence + Deterministic
Comparison. Sprint plan: `product-backlog/sprints/sprint-14-billing-identity.md`.
Scoping decisions (2026-09-08): start now on the fixtures/mock build; pilot identity =
known/manual (OQ-001 deferred); real Galaxion read-only adapter + real-data validation
in scope (OQ-003/004 answered as data arrives, INFRA-017). Amounts are tax-included
(TTC), confirmed 2026-09-09.

Grounding docs: `docs/integrations/galaxion/bss-billing-data-model.md` (real BSS model),
`invoice-extraction-json.md` (normalized contract), `galaxion-billing-contracts.md`
(`billing-api` routes), ADR-0003/0004/0005.

---

## TASK-BE-038 — Billing domain model

**Type:** Technical task (backend domain)
**Status:** ✅ Validated + merged into `feat/sprint-14-billing-identity` (2026-09-10, `--no-ff`)
**Parent:** EPIC-004 / US-010/011/012/013 · ADR-0003
**Gate:** none (fixture-buildable)

### Context

The billing assistant needs a pure domain model to represent an invoice, its lines,
the comparison of two invoices, and the business causes of a delta — with amounts as a
first-class `Money` value object (never `double`/bare `long`). The model mirrors the
real BSS hierarchy `invoice → invoice_section → invoice_group → invoice_item` with
amounts at each level (`bss-billing-data-model.md`), so the future `billing-api` adapter
and the PDF extractor both map onto the same shape (ADR-0004/0005).

This is a **new bounded context** `com.voicesupport.billing` following the Hive/
hexagonal layout used by `conversation` and `knowledge` (pure domain, no Spring).

### Scope

- `Money` value object (integer minor units + currency; add/subtract/negate/abs,
  same-currency guard) — the domain amount type; adapters convert at the boundary.
- Typed identifiers: `InvoiceId`, `AccountId` (sanitized records).
- `LineAmounts` (tax-included / tax-excluded / tax), `BillingPeriod`, `Evidence`,
  `InvoiceLevel`, `LineCategory` value objects.
- Invoice hierarchy entities: `Invoice` → `InvoiceSection` → `InvoiceGroup` →
  `InvoiceItem`, with a helper to flatten to the billed lines.
- Comparison output types (data only, populated by TASK-BE-042): `ChangeKind`,
  `LineDelta`, `BillingCauseType`, `BillingCause`, `InvoiceComparison`.

### Out of scope

- The comparison **logic** (diff/attribution/reconciliation) → TASK-BE-042.
- Any BSS access, adapter, PDF extraction, or Spring wiring.

### Acceptance

- Pure domain, no Spring/infra/other-context dependency (ArchUnit green).
- `Money` rejects cross-currency operations; all monetary fields use `Money`.
- Value objects are immutable records with compact-constructor validation.
- `Invoice.lines()` returns all `InvoiceItem` across the section/group tree.
- Amounts are tax-included as the customer-facing basis (`LineAmounts.taxIncluded()`).
- Unit tests cover `Money` arithmetic/guards, id sanitization, `LineAmounts`, and the
  invoice flatten helper. `mvn test` green.

### Notes

- Amount **unit** (euros vs cents) and `crud_amount` meaning are pending Galaxion
  (INFRA-017); the domain fixes the type as integer minor units per
  `invoice-extraction-json.md`, and the adapter will convert once confirmed.

---

## TASK-BE-039 — `BssBillingPort` + use cases

**Type:** Technical task (backend port)
**Status:** ✅ Validated by user (2026-09-10) — `task/TASK-BE-039-bss-billing-port` (merge-ready; not merged). Adversarial review 96/100.
**Parent:** US-005 · ADR-0004
**Gate:** none (fixture-buildable)

### Context

A typed **read-only** outbound port to retrieve billing evidence (invoices, comparable
periods) so the domain never talks to the BSS directly. Mirrors the
`bill-periods → bill-runs → bill-run-accounts → documents/composed` flow of
`billing-api` without binding to it.

### Scope

- `BssBillingPort` (outbound): list comparable invoices/periods for an account, fetch an
  invoice by reference — returning the TASK-BE-038 domain model.
- Inbound use case(s) for "retrieve available invoices/periods" (US-005).
- No live adapter (mock in TASK-BE-040).

### Acceptance

- Port is an interface in `billing/domain/port/out`, read-only (no mutation).
- Use case returns domain types; ArchUnit + naming green.

### Deferred (adversarial review 2026-09-10)

- `availableInvoices` returns **all** invoices of the account, ordered most-recent-first
  (deterministic tie-break by invoice id). Restricting to **like-for-like comparability**
  (same `InvoiceLevel` / subscription) and **selecting the pair** to compare are deferred
  to **TASK-BE-041/042**. The account scoping (BR-002-1) is exercised by a service test;
  the fail-closed enforcement lives in the adapters (TASK-BE-040/047).

---

## TASK-BE-040 — BSS mock adapter + fixtures

**Type:** Technical task (backend adapter + fixtures)
**Status:** ✅ Validated + merged into `feat/sprint-14-billing-identity` (2026-09-10, `--no-ff`). Adversarial review 94/100. Follow-up for BE-045: prod `source` default + OTel on billing path.
**Parent:** US-005/007 · ADR-0004 · BR-003-3
**Gate:** none (fixtures)

### Context

An API-compatible in-memory/mock adapter behind `BssBillingPort` with static fixtures
`customer-eir-001…006` covering the V1 journeys (nominal, discount expiry, overage,
proration, insufficient data, unusable), so the engine is testable before real access.

### Scope

- Mock adapter implementing `BssBillingPort` (profile-gated bean).
- Fixture set `customer-eir-001…006` with an expected product behaviour each.

### Acceptance

- Each fixture loads into the domain model and drives a QA journey (TASK-QA-019).
- Adapter is swappable by config with the future real adapter (TASK-BE-047).

---

## TASK-BE-042 — Deterministic comparison engine

**Type:** Technical task (backend domain)
**Status:** ✅ Validated + merged into `feat/sprint-14-billing-identity` (2026-09-10, `--no-ff`). Adversarial review 94/100.
**Parent:** US-010/011/012/013 · ADR-0003 · DEC-002 · BR-003
**Gate:** none (fixture-buildable)

### Context

The core billing reasoning: compare two invoices deterministically and produce the
line deltas, the attributed business causes, and the residual the lines do not
account for. Amounts and causes are computed **by code** — the LLM only phrases this
grounded result (DEC-002); it never computes anything.

### Scope

- Inbound `CompareInvoicesUseCase` + pure `InvoiceComparisonService`.
- Match lines by code across the two invoices (fallback to `type`/category label).
- Signed contribution per line on the **tax-included (TTC)** basis; `ChangeKind`
  (appeared / disappeared / changed) per line.
- Attribute each non-zero delta to a `BillingCauseType` from its `LineCategory`
  (deterministic table); unmapped categories fall to `UNEXPLAINED`.
- Reconciliation: expose `unexplainedAmount` = header `totalDelta` − Σ line
  contributions, so a header/line gap is always **surfaced, never hidden** (BR-003).
- Register both use-case beans in `BillingConfig`.

### Acceptance

- Pure domain, no Spring/infra dependency (ArchUnit green).
- The four comparable eir journeys attribute the expected cause (discount expiry,
  overage, proration; nominal = no change) with a fully-explained (zero) residual.
- A header/line mismatch yields a non-zero `unexplainedAmount`.
- Unit tests drive the engine off `BssBillingFixtures`. `mvn test` green.

### Out of scope

- Evidence-sufficiency / confidence gate → TASK-BE-043.
- Like-for-like pair selection & `InvoiceLevel` matching → carried from BE-039 note.
- PDF extraction path → TASK-BE-041.

## TASK-BE-043 — Evidence-sufficiency / confidence gate

**Type:** Technical task (backend domain)
**Status:** ✅ Validated + merged into `feat/sprint-14-billing-identity` (2026-09-10, `--no-ff`). Adversarial review 93/100.
**Parent:** US-012/013 · ADR-0003 · DEC-002 · BR-003 · OQ-002 (provisional thresholds)
**Gate:** OQ-002 (provisional — thresholds tunable, refined when confidence policy is confirmed)

### Context

Before the LLM phrases a billing explanation (DEC-002), the deterministic result
must be judged **safe to explain**. This gate turns an `InvoiceComparison` into an
`ExplanationReadiness` verdict so the answer engine (BE-045) can phrase, phrase with
a caveat, or withhold + escalate — with a traceable reason and the residual amount.

### Scope

- Inbound `AssessComparisonReadinessUseCase` + pure `ComparisonConfidenceService`.
- Verdict model in the domain: `ExplanationConfidence` (EXPLAINABLE / PARTIAL /
  INSUFFICIENT), `ReadinessReason`, `ExplanationReadiness` (confidence, reason,
  `escalate`, `unexplainedAmount`).
- Deterministic rules: no usable billed line on either side → INSUFFICIENT/escalate
  (distinguishes the *unusable* journey from a genuine no-change); zero residual →
  EXPLAINABLE; residual within `max-residual-ratio` of the total → PARTIAL; else
  INSUFFICIENT/escalate.
- Configurable provisional ratio (`voice-support.billing.confidence.max-residual-ratio`,
  default 0.05); bean wired in `BillingConfig`.

### Acceptance

- Pure domain, no Spring/infra dependency (ArchUnit green).
- Fully-reconciled fixture journeys → EXPLAINABLE; the unusable journey → INSUFFICIENT
  (NO_USABLE_LINES, escalate); a small residual → PARTIAL; a large residual →
  INSUFFICIENT (RESIDUAL_TOO_HIGH, escalate). Residual always surfaced (BR-003).
- Unit tests drive the gate off real comparisons. `mvn test` green.

### Out of scope

- Wiring into the answer engine / escalation content → TASK-BE-045.
- Final confidence policy & thresholds → OQ-002 resolution.

## TASK-BE-041 — Invoice PDF extractor → structured invoice (fallback path)

**Type:** Technical task (backend domain + synthetic adapter)
**Status:** ✅ Validated + merged into `feat/sprint-14-billing-identity` (2026-09-10, `--no-ff`). Adversarial review 93/100.
**Parent:** US-005/007 · ADR-0005 · BR-003
**Gate:** none (synthetic; real PDFBox parser deferred until real PDFs)

### Context

ADR-0005 fallback: when the structured BSS source (`GET /invoices/composed`) is not
reachable read-only, the invoice PDF is extracted into the **same domain model**
before any comparison — the LLM never reads the PDF. Because no real PDFs exist yet,
BE-041 delivers the **contract + a synthetic extractor** (mock-first, like the BSS
mock adapter); the real PDFBox parser registers later once real PDFs are provided.

### Scope

- Outbound `InvoicePdfExtractorPort` (`ExtractionResult extract(PdfSource)`).
- Value objects: `PdfSource` (reference + defensively-copied bytes), `ExtractionStatus`
  (SUCCESS / PARTIAL / FAILED), `ExtractionResult` (status + optional invoice + issues,
  invariant-checked — a FAILED result carries no invoice, a non-FAILED one must).
- `FixtureInvoicePdfExtractorAdapter`: maps a reference (fixture period id) to a structured
  invoice; `-partial` suffix → PARTIAL with issues; empty/unknown → FAILED.
- Bean wired in `BillingConfig` (`voice-support.billing.pdf.source`, default `fixture`).

### Acceptance

- Extraction **status is first-class** so a partial/failed extraction is never treated
  as complete (BR-003).
- Pure domain contract + infra adapter; ArchUnit green; context boots.
- Unit tests: success / partial / empty-doc failed / unknown-ref failed / null guard;
  `PdfSource` defensive copy + blank rejection; `ExtractionResult` invariants.
  `mvn test` green.

### Out of scope

- Real PDF parsing (PDFBox) & real-invoice validation → deferred (with TASK-BE-047 / QA-020).
- Choosing structured-source-vs-PDF at runtime → TASK-BE-045.

## TASK-BE-044 — Customer identity resolution (pilot mode) + ADR-0050

**Type:** Technical task (backend domain + synthetic adapter) + ADR
**Status:** ✅ Validated + merged into `feat/sprint-14-billing-identity` (2026-09-10, `--no-ff`). Adversarial review 93/100. ADR-0050 Accepted.
**Parent:** BR-002-1 · ADR-0004 · **ADR-0050** · OQ-001 (verification strength, pilot)
**Gate:** OQ-001 (pilot trust model — real verification deferred)

### Context

Every billing access is scoped by `AccountId` (BR-002-1, fail-closed), but nothing yet
turns *who is on the call/chat* into that account. The pilot has no strong auth
(OQ-001) and runs on synthetic accounts, so BE-044 delivers the **fail-closed identity
seam** (decision recorded in **ADR-0050**) that BE-045 will call before any BSS access.

### Scope

- Inbound `ResolveCustomerIdentityUseCase` + pure `CustomerIdentityService`.
- Outbound `CustomerDirectoryPort` (returns matches; domain decides the verdict).
- Value objects: `IdentityClaim` (channel + reference, sanitized, never logged in
  clear), `IdentityStatus` (RESOLVED / UNRESOLVED / AMBIGUOUS), `IdentityResolution`
  (status + optional account, invariant-checked, `canAccessBilling()`).
- Resolution: **0 → UNRESOLVED, 1 → RESOLVED, ≥2 → AMBIGUOUS**; only RESOLVED grants
  access — no/ambiguous match never yields an account (fail-closed).
- `InMemoryCustomerDirectoryAdapter` (pilot) aligned with `customer-eir-*` fixtures,
  case-insensitive, incl. an intentionally ambiguous reference; beans in `BillingConfig`.

### Acceptance

- Fail-closed: a caller can never obtain an `AccountId` without an unambiguous match.
- Pure domain + infra adapter; ArchUnit green; context boots.
- Unit tests: single/none/ambiguous match + null guards; adapter known/unknown/ambiguous
  + case-insensitive; `IdentityResolution` + `IdentityClaim` invariants. `mvn test` green.
- **ADR-0050** written + indexed.

### Out of scope

- Strong authentication / verification strength → OQ-001.
- Wiring identity → billing access in the answer flow, escalation on unresolved → TASK-BE-045.

## TASK-BE-045 — Wire billing chain behind the answer engine

**Type:** Technical task (backend integration) — **runtime-affecting** (OTel mandatory)
**Status:** ✅ Validated (user, 2026-09-11) — `task/TASK-BE-045-wire-billing-chain`,
pushed. Design in `docs/architecture/billing-answer-integration-cadrage.md`;
**decisions D1–D3 locked** (D1a evidence injection · D2a deterministic intent detector ·
D3c dedicated `POST /api/conversation/billing-explain`). **ADR-0052 Accepted.** Sub-tasks
1–8 done: `BillingIntentDetector` + `BillingExplanationComposer` + `ExplainBillingUseCase`
(billing core, 18 tests); `BillingExplanationPort`/`InProcBillingExplanationAdapter` seam +
`BillingAnswerService` + `POST /api/conversation/billing-explain` (10 tests);
`EscalationReason` += IDENTITY_UNVERIFIED/BILLING_UNEXPLAINED; BILLING OTel slice.
Full backend suite (560 tests) + ArchUnit green, Spring context boots. Adversarial review
**93/100** (QA gate: Pass). **QA functional+latency: GO** (2026-09-11) — 8 Cucumber
acceptance scenarios (`billing-explanation.feature`, BDD suite 44 green), api-key gating +
DEC-002 block covered; `billing` deterministic slice p50 2.5µs/p95 6.4µs/p99 17.6µs (mock
BSS), LLM slice unchanged from `/answer`. Report: `docs/qa/task-be-045-billing-explain-qa-report.md`.
**Merge-ready** into `feat/sprint-14-billing-identity` (`--no-ff`) — awaiting explicit merge request.
**Parent:** US-005/007/010–013 · ADR-0003 · **DEC-002** · BR-002-1 · BR-003 · ADR-0019
**Gate:** BE-038/039/040/041/042/043/044 (all merged)

### Cadrage summary

Connect identity → comparable invoices → comparison → confidence gate to the existing
answer engine so the LLM **only phrases** a grounded, pre-computed result (DEC-002) and
the bot **escalates fail-closed** on unresolved identity or non-explainable results.
Verified constraints: no runtime intent classifier (BUG-007), no identity field on
`ConverseRequest`, LLM grounding is only `List<RetrievedEvidence>` (OutputGuardrail vets
amounts). Locked decisions: **D1a** deterministic result reaches the LLM as injected grounding
evidence (reuse AnswerGeneratorPort + OutputGuardrail, DEC-002 by construction); **D2a**
deterministic FR/EN billing-intent detector behind a port; **D3c** a dedicated
`POST /api/conversation/billing-explain` endpoint (leave `/converse` + runtime to a
follow-up). Next: write **ADR-0052**, then implement the 9 sub-tasks (full target flow +
escalation + mandatory OTel slice + sub-tasks in the cadrage doc).

## TASK-BE-046 — Billing KB entries for confirmed causes

**Type:** Knowledge-base content (FR) — **not runtime-affecting** (no code; no OTel change)
**Status:** ✅ Validated + merged into `feat/sprint-14-billing-identity` (2026-09-14, `--no-ff`). Editorial pass applied (hors-forfait factual fix, cross-reference, wording trim); KB tests green.
**Parent:** US-005/010–013 · **BR-003** · ADR-0030 (domain tagging at ingestion)
**Gate:** BE-040 (comparison `BillingCauseType`), BE-045 (explanation path)

### Cadrage summary

The deterministic comparison engine attributes each invoice delta to a `BillingCauseType`
(`DISCOUNT_EXPIRY`, `USAGE_OVERAGE`, `OPTION_CHANGE`, `PRORATION`, `TAX`, `ONE_OFF_FEE`,
`ADJUSTMENT`, plus the fail-closed `UNEXPLAINED`). BE-045 phrases the customer's *own*
computed result from injected evidence, but the generic RAG path (`/converse`, `/answer`)
had no dedicated, retrievable explanation of **what each confirmed cause means**. BE-046
adds one customer-facing KB entry per confirmed cause to `knowledge-base/billing-faq.md`
(`domain: billing`, `language: fr`), so a general "pourquoi ma facture a changé" question
retrieves a clear, evidence-backed explanation — **no invented amounts, no policy claims**,
purely educational (what the cause is, how to check it, what to do). The fail-closed
`UNEXPLAINED` case is covered by a "montant que nous ne pouvons pas expliquer → mise en
relation conseiller" entry (BR-003 / ADR-0019).

### Acceptance

- One retrievable section per confirmed `BillingCauseType`, in French, customer language.
- Aligned 1:1 with the engine taxonomy (a reviewer can map each section to an enum value).
- No fabricated figures, no account-specific data; consistent with existing billing FAQ.
- Front-matter preserved (`domain: billing`), so ingestion tags the chunks `billing`.
- Markdown well-formed (`git diff --check`); existing KB tests stay green.

## TASK-QA-019 — Billing fixtures + Gherkin journeys + latency slices

**Type:** QA (functional + latency) — validates the billing socle end-to-end
**Status:** ✅ Validated + merged into `feat/sprint-14-billing-identity` (2026-09-14, `--no-ff`). Six-journey matrix Pass; BDD 46 green, full backend 571 green; report GO.
**Parent:** US-005/007/010–013 · **DEC-002** · BR-002-1 · BR-003 · ADR-0019 · ADR-0052
**Gate:** BE-038→046 (billing socle, all merged)

### Cadrage summary

Consolidate QA acceptance over the **six canonical fixture journeys** (`BssBillingFixtures`,
accounts `eir-001..006`): nominal (unchanged), discount expiry, usage overage, proration,
insufficient data (single invoice), unusable (no billable lines). BE-045 QA already covered
four journeys + DEC-002 + identity + non-billing through `POST /api/conversation/billing-explain`;
QA-019 **completes the matrix** by adding the missing grounded journeys (usage overage,
proration) so every fixture journey has an explicit product-observable acceptance scenario,
and formalizes the QA report + latency slice for the billing socle.

Automation layer: **Cucumber for Java** (`billing-explanation.feature`, 10 scenarios,
`RunKnowledgeBddTest` suite 46 green). **Behave is N/A** here — the billing socle is a pure
backend chain with no Python voice-runtime behavior; Behave stays reserved for the voice
runtime (STT/TTS/turn/barge-in).

### Acceptance

- The six fixture journeys each map to a product-observable scenario (grounded or degraded).
- DEC-002 amount-grounding block, identity fail-closed, and non-billing redirect covered.
- `billing` OTel slice measured (deterministic chain) and reported; LLM slice attribution stated.
- QA report `docs/qa/task-qa-019-billing-journeys-qa-report.md` with the journey matrix,
  latency and residual risks; defects (if any) logged as bug tickets.

## TASK-BE-047 — Real Eir read-only adapter behind `BssBillingPort`

**Type:** Backend integration — **runtime-affecting** (default `source=mock`, no runtime change yet)
**Status:** ✅ Merged + shipped since **v0.9.0** via the Sprint-14 closure (`5650e15`; live-validated on EIR test account 5) — status reconciled by git ancestry 2026-09-29. Originally `task/TASK-BE-047-eir-bss-adapter` (off `feat/sprint-14-billing-identity`).
First slice implemented: the **enquiry-based structured path** behind `BssBillingPort`, config-selected
(`source=mock` default → `eir`), independent per-service clients, mapped to the billing domain, unit-tested
without network (577 backend tests green). **Blocked for validation** on a real test account + sample
payloads (OQ-003 cents-vs-pennies, real `details`/CSV shape) → QA-020.
**Parent:** US-005/007/010–013 · ADR-0004 · BR-002-1 · OQ-003/004
**Gate:** BE-038→046 (billing socle merged) · real access (INFRA-017)

### Input received (2026-09-14)

Real Eir dev OpenAPI specs for `billing-enquiry-service` (3.1.0) + `billing-service` (2.3.1) —
contract analysis, port mapping and the **independent-adapter design** in
`docs/integrations/galaxion/eir-billing-services-contract.md` (specs versioned under
`docs/integrations/galaxion/assets/`). Answers OQ-003 unit (amounts are `int64`), reveals a
structured enquiry breakdown (PDF becomes fallback) + a CSV `detail-report` line source.

### Implemented (this slice)

- Two independent per-service seams (interfaces) — `BillingEnquiryClient` (invoice breakdown) and
  `BillingServiceClient` (account invoice list) — with `RestClient` adapters
  (`RestBillingEnquiryAdapter` / `RestBillingServiceAdapter`) sending the two `galaxion-user-*`
  authorization headers; 404 → empty, other errors → sanitized 503.
- `EirBssBillingAdapter implements BssBillingPort` composes both clients and maps their DTOs onto the
  domain (`Invoice`/`InvoiceSummary`/`LineAmounts`); **no Eir type crosses the adapter boundary**.
  The enquiry breakdown (recurring/oneOff/usage/vat/total) becomes a single synthetic invoice group;
  totals use the TTC `invoiceAmount` + tax split; lines reconcile to the total.
- DTOs pinned with `@JsonProperty` (immune to the backend's global SNAKE_CASE) and nested in the
  client interfaces (keeps the `..adapter.out..` naming convention clean).
- Config-driven selection + settings (`voice-support.billing.bss.source`,
  `…bss.eir.{enquiry-base-url,service-base-url,currency,user-type,user-identifier,connect-ms,read-ms}`),
  **`mock` default** so nothing changes at runtime until validated.
- Tests: `EirBssBillingAdapterTest` (mapping + fail-closed: non-numeric id, not-found, skip unusable),
  `EirBillingJsonMappingTest` (camelCase-under-SNAKE_CASE guard). ArchUnit green.

### Adversarial review

`docs/qa/task-be-047-eir-bss-adapter-review.md` — **91/100, QA gate Pass** for the mock-default slice.
One blocking finding (BSS hop not observable) **fixed** (`slice=bss`, `provider=eir`). BR-002-1
`fetchInvoice` ownership check now **implemented** (see below); the remaining real-data validations stay
**accepted residuals**, prerequisites to enabling `source=eir` (not to merge).

### Live-validated against test account 5 (2026-09-15)

Real calls to the Eir dev services (see `docs/integrations/galaxion/eir-billing-services-contract.md`
§ Live validation) confirmed and fixed several things:

- **Unit = cents** (`amount 3999` = €39.99); **`invoiceId` == `invoiceNumber`**; **`accountId` = 5 (int)**
  → BR-002-1 numeric ownership guard validated on real data.
- **Account-id linkage confirmed:** billing-service `account_id` (string) **==** enquiry `billingAccountId`
  (int64). `fetchInvoice` enforces **BR-002-1 defense-in-depth** (numeric owner compare, fail-closed).
  Test: `fetchInvoice_failsClosedWhenInvoiceBelongsToAnotherAccount`.
- **Mapping bug fixed:** `vatAmount` is **inside** `invoiceAmount` (TTC), not additive
  (`invoiceAmount 3999 == recurringAmount 3999`, `vat 748` = 23% inside). The adapter no longer emits a
  separate TAX line; category (TTC) lines reconcile to `invoiceAmount`, VAT stays in the totals split.
  Tests: `fetchInvoice_mapsRealAccount5Breakdown_vatStaysInsideTheTotal`, `…_multiCategoryLinesReconcileToTheTtcTotal`.

### Still open before enabling `source=eir` (→ QA-020)

- **Archive token** required by `detail-report` (CSV) / `summary-report` (PDF) — both return **HTTP 412
  `archive-file-token-is-null`** without it → line-level cause attribution (discount/option/proration)
  blocked until the token/flow is provided; until then those deltas surface as `UNEXPLAINED` (fail-closed).
- A **two-invoice** account (or a second period) — account 5 has a single invoice, so no real delta to
  compare yet.
- Does `invoiceAmount` include previous balance / payments, or only current-period lines?
- identity → `galaxion-user-*` header derivation (pilot uses a configured default; coordination P4).

## TASK-BE-048 — Billing escalation `reason` telemetry dimension

**Type:** Technical task (backend observability) — **runtime-affecting** (OTel dimension added)
**Status:** ✅ Validated + merged into `feat/sprint-14-billing-identity` (2026-09-16, `--no-ff`).
Adversarial review **96/100 PASS** (`docs/qa/task-be-048-billing-reason-telemetry-review.md`); backend
583 green. Follow-up to the BUG-020 review (Info finding): the `billing` slice `outcome=not_enough_data`
collapsed three distinct escalation situations, so Ops/QA could not tell an unfetchable-evidence
escalation from a genuine no-data one.
**Parent:** BUG-020 review · BR-003 · ADR-0028
**Gate:** none

### Context

`InProcBillingExplanationAdapter` records the `billing` slice tagged only by `outcome`
(`explanation.outcome()`). Three different domain situations all surface as `not_enough_data`:
fewer than two comparable invoices, a listed-but-unfetchable invoice (BUG-020: BSS race / BR-002-1
ownership drop), and the confidence gate's INSUFFICIENT verdict (`NO_USABLE_LINES` /
`RESIDUAL_TOO_HIGH`). They are operationally different (data gap vs evidence-fetch failure vs
reconciliation gap) but indistinguishable in metrics/logs.

### Scope

- Add an optional stable `reason` code to `BillingExplanation` (nullable; set on the not-enough-data
  paths): `insufficient_history`, `evidence_unfetchable`, `no_usable_lines`, `residual_too_high`.
- `BillingExplanationService` sets the reason at each not-enough-data producer (including the BUG-020
  empty-comparison path and the gate's INSUFFICIENT reasons).
- Add a consistent `reason` tag (default `n/a`) to the `voice_support.slice` timer + `[TELEMETRY]`
  log via `BackendTelemetry` (kept uniform across all slices so tag keys stay consistent); a new
  `recordLatency(slice, provider, outcome, reason, elapsed)` overload; the billing adapter passes the
  domain reason.

### Acceptance

- `outcome` tag stays stable (`not_enough_data`); the `reason` tag distinguishes the three cases.
- All other slices keep recording (with `reason=n/a`); existing telemetry lookups stay green (tag
  filters are subset matches).
- Unit tests: the adapter records the right `reason` per not-enough-data situation; non-escalating
  outcomes record `reason=n/a`. Full backend suite green. No PII in the new dimension.

---

## TASK-INFRA-017 — Galaxion inputs coordination package

**Type:** Doc / coordination — **not runtime-affecting** (no code; no OTel change)
**Status:** ✅ Request **finalized — ready to send** (2026-09-16). Refreshed after the live
validation on test account 5: records what the live test resolved (unit=cents, VAT-inside-total,
identifier linkage, auth headers, RFC 7807 errors) and narrows the outstanding asks to two concrete
P1 blockers. Deliverable: `docs/integrations/galaxion/galaxion-coordination-request.md`.
**Parent:** OQ-001/003/004 · INFRA-017
**Gate:** — (parallel track; unblocks BE-047 real-data + QA-020)

### Context

Consolidates and prioritizes everything still needed from the Galaxion / BSS side to validate V1 on
real data, with an owner per item and a ready-to-send email cover. The build never waits on these
(fixtures/mock, `source=mock` default); they gate **real-data acceptance (QA-020)** and enabling
`source=eir` for line-level cause attribution.

### Finalized asks (post account-5 live validation)

- **P1 — Archive token:** `detail-report` (CSV) + `summary-report` (PDF) return HTTP 412
  `archive-file-token-is-null`; `details` is empty. Without line detail, sub-`recurringAmount` deltas
  (discount/option/proration) stay `UNEXPLAINED` (fail-closed). Need the token flow.
- **P1 — Two-invoice account:** account 5 has a single invoice → no real delta to compare (QA-020).
- **P2:** `invoiceAmount` composition (current-period vs balance/payments); line catalogue
  (`type`/`code`/`vatType` or CSV columns) → business-cause mapping; CSV column shape.
- **P3:** error/edge-case behaviour + pagination; per-cause evidence + accepted customer wording.
- **P4 (deferred):** customer identification + `galaxion-user-*` header derivation + log masking (OQ-001).

### Resolved by the live test (recorded so Galaxion does not re-answer)

Unit = cents; VAT contained in the total; `invoiceId` == `invoiceNumber`; enquiry `billingAccountId`
== billing-service `account_id` (one identifier space); auth via `galaxion-user-type|identifier`
headers; RFC 7807 error format.

### Acceptance

- Prioritized asks with owners + ready-to-send email cover (done).
- Live-validated facts recorded as "do not re-answer" (done).
- Markdown well-formed (`git diff --check`).

## Proposed (later this sprint — full sections created when picked up)

| Ticket | Title | Gate |
|--------|-------|------|
| TASK-QA-020 | Real-data validation on provided anonymized PDFs/payloads | real data + INFRA-017 P1 answers |

---

## TASK-BE-059 — Validate the invoice model on real eir B2C PDFs + realistic mock data

**Type:** Technical task (domain model + fixtures + docs)
**Status:** ✅ Merged into `feat/restart-from-scratch` (2026-09-30, `--no-ff` `5940dcb`) — full backend suite green, ArchUnit green.
**Priority:** High
**Depends on:** TASK-BE-040 (mock BSS), TASK-BE-042 (comparison), ADR-0005/0052
**Decision:** ADR-0054

### Context

Three anonymized real eir B2C invoice PDFs (accounts `99224964`, `99226126`, `99226337`, two bill
runs each) were provided to validate the V1 billing model and to seed realistic mock data. Validation
(see `docs/integrations/galaxion/eir-b2c-invoice-samples.md`) confirmed the `Invoice → Section →
Group → Item` hierarchy and exact tax-included reconciliation on all six invoices, and surfaced an
ordering bug plus a missing per-line period.

### Scope

- **Model (ADR-0054):** new `DateRange(start,end)` VO; `BillingPeriod` extended to
  `(id, invoiceDate, usagePeriod, chargePeriod)` with `orderingDate()`; nullable `DateRange period`
  on `InvoiceItem`/`InvoiceGroup`. All new ranges nullable + backward-compatible secondary
  constructors (zero churn, kept flexible).
- **Ordering fix:** `ComparableInvoiceService` orders by `orderingDate()` (usage-period start, else
  issue date) so identical "Billing date" no longer inverts current/previous.
- **Mock data:** `EirB2cSampleFixtures` (6 invoices, real account numbers, 23% VAT, prorata line
  periods, distinct codes for recurring vs prorated variants) merged into the mock `BssBillingPort` +
  PDF fallback; the three accounts resolvable by number in the mock customer directory.
- **Docs:** ADR-0054 + `eir-b2c-invoice-samples.md` (validation, open-question answers, gaps).

### Acceptance

- Each of the six invoices reconciles exactly on TTC (`Σ line TTC = total TTC`) — tested.
- The comparator returns September (later usage period) as *current* despite an identical issue date
  — regression test added.
- Proratas carry an explicit `DateRange` period — tested.
- Existing call sites/tests compile unchanged (secondary constructors); `mvn test` + ArchUnit green.

### Out Of Scope / Residual

- `chargePeriod` stored but not yet consumed by the explanation composer (advance-billing wording).
- Previous-balance / payments / amount-due at invoice level (nil on these samples).
- Real PDF parser (ADR-0005 fallback) — still the synthetic fixture extractor.
- Line-period is descriptive only; comparison matching stays by label/code.

**Adversarial review 93/100 (Pass, 2026-09-29)** — no blocking finding; full review at
`docs/qa/task-be-059-adversarial-review.md`. Residual (accepted): fixtures class > 200 lines (pure
data); `chargePeriod` + line period stored but not yet surfaced in customer wording.

---

## TASK-BE-060 — Cause attribution for multi-service invoices (new/removed service, one-off fees)

**Type:** Technical task (billing comparison + confidence)
**Status:** 📋 Proposed (follow-up surfaced by TASK-BE-059 on real eir B2C mock data)
**Priority:** High
**Depends on:** TASK-BE-042 (comparison), TASK-BE-043 (confidence gate), TASK-BE-059 (real mock data)
**Relates to:** OQ-002 (residual ratio), ADR-0052

### Context

Replaying the deterministic billing chain over the real eir B2C mock samples (TASK-BE-059) shows V1
explains the **single-service** delta cleanly (account `99224964`: "+55.47 € … option change +16.98,
pro-rata +8.50, one-off +29.99"), but **fails closed** on the two **multi-service** accounts:

- `99226126` (Fibre → Fibre+TV) → `NOT_ENOUGH_DATA` / `residual_too_high`
- `99226337` (Fibre+TV → +Mobile) → `NOT_ENOUGH_DATA` / `residual_too_high`

Root cause: the comparison keys deltas by line label/code, so **a whole service section appearing or
disappearing** (new eir TV / new Mobile) and **one-off charges being removed** (FTTH installation,
broadband activation) do not map onto a `BillingCauseType`; the unexplained residual exceeds the 5%
gate → safe escalation (correct fail-closed behaviour, but a poor customer answer for a common case).

### Scope

- Map structural changes to typed causes: **NEW_SERVICE / SERVICE_REMOVED** (a section present on one
  side only) and **ONE_OFF removal/appearance** aggregated at group level.
- Compose a customer-facing line for those causes ("un nouveau service … / des frais ponctuels du mois
  dernier qui disparaissent").
- Re-examine the 5% `max-residual-ratio` gate for multi-service invoices (OQ-002): a fully attributed
  structural change should be EXPLAINABLE, not escalated.

### Acceptance

- `99226126` and `99226337` Aug→Sep deltas are **EXPLAINABLE** (or PARTIAL with a bounded residual),
  not escalated, with grounded per-cause amounts summing to the total delta.
- The single-service case (`99224964`) stays EXPLAINED.
- New non-regression tests use the TASK-BE-059 eir B2C fixtures.
- Fail-closed preserved for genuinely unexplained residuals.

### Out Of Scope

- Live BSS / real PDF parsing (still fixtures).
- Routing billing from `/converse` (separate follow-up).

---

## TASK-BE-061 — Channel-provided customer identity + RAG↔billing routing on `/converse`

**Type:** Technical task (conversation routing + channel identity) — routing ADR created (ADR-0055)
**Status:** ✅ Merged into `feat/restart-from-scratch` (2026-09-30, `--no-ff` `5940dcb`) — reshaped to channel-provided identity as the **primary** path (vocal collection dropped to a fallback / out of scope)
**Priority:** High
**Depends on:** TASK-BE-045 (billing chain), ADR-0052 (billing seam), ADR-0050 (identity), US-042 (language)
**Relates to:** ADR-0055 (routing decision), BR-002-1 (identity), OQ-001 (identity source), BUG-026 (session-locked envelope)

### Context

Today the customer-facing loop (web/voice) calls `POST /api/conversation/converse` → **RAG only**. The
deterministic billing chain lives behind a **separate** endpoint `POST /api/conversation/billing-explain`
that the voice runtime never calls, and it needs a customer `reference` (account number) that the main
loop never collects. So a real "I don't understand, my bill is higher than last month" spoken in the app
got a **generic KB answer**, never a real invoice comparison.

**Reshape (2026-09-29).** Rather than asking the customer to dictate the account number vocally, we align
with the **target** architecture where identity is asserted by the **channel up front** (Genesys ANI / an
authenticated header or query param — ADR-0050 channel-provided reference). The reference is carried as
ambient session identity into `/converse`; vocal collection of the number is **out of scope** (a fallback
for later, never the primary path). See ADR-0055.

### What was built

1. **Channel identity up front.** The pilot web UI (`ws.html`/`webrtc.html`/`index.html`) gains an account
   **listbox** — the 3 eir B2C sample accounts (`99224964`, `99226126`, `99226337`) + a **"Sans compte"**
   default. The choice is sent once per connection (`?account_id=` on WS/batch, `account_id` in the WebRTC
   offer body), threaded through `ChannelEnvelope.account_reference` (session-locked, like the BUG-026
   language lock) → `AnswerRequest` → `/converse` body `account_id`. This **simulates** the target
   header/param with zero conversation-engine change when the real channel is wired.
2. **Routing on `/converse`.** New application `ConversationRoutingService` (`ConversationRoutingUseCase`);
   `ConverseController` depends on it instead of `ConverseUseCase`. Routes to the billing chain
   (`AnswerBillingQuestionUseCase`) **iff** an account reference is present **and** `BillingIntentDetector`
   flags a billing question (ADR-0052 D2a); otherwise RAG. **"No account" + billing question → RAG generic**
   (fail-safe — never guess whose invoice to open).
3. **Cross-context seam (no type leakage).** Billing-intent stays a single source of truth exposed via a
   published `DetectBillingIntentUseCase` (billing `port/in`) and consumed through the conversation out-port
   `BillingIntentPort` via `InProcBillingIntentAdapter` (mirrors the ADR-0052 `BillingExplanationPort` seam).
4. **Fail-closed + DEC-002 unchanged** (the ADR-0052 chain is only *reached*, not modified).

### Acceptance (met)

- With an account selected and a billing turn, `/converse` returns a grounded comparison (or a fail-closed
  safe hand-off) — no separate endpoint call by the user. ✅
- "Sans compte" (no `account_id`), or a non-billing turn, keeps the RAG path unchanged. ✅
- Regression tests lock both branches (`ConversationRoutingServiceTest`: billing vs RAG vs no-account vs
  language forwarding); Python threading tests (`test_http_backend`, `test_websocket_app`). ✅
- OpenTelemetry / logs: `[ROUTE] route={billing|rag} account_ref_present={}` (never the value);
  `account_ref_present` on the Python envelope telemetry. Reference (personal data) never logged in clear. ✅
- ADR created (ADR-0055). ✅

### Out Of Scope

- **Vocal collection** of the account number (slot-filling, digit-over-STT robustness, max-retries) — a
  fallback for a later ticket; the channel supplies identity in the primary path.
- Improving multi-service cause attribution (TASK-BE-060).
- Live BSS / real PDF parsing (still fixtures).
- Strong customer authentication (OQ-001) — pilot accepts a channel-provided reference at a low bar.

**Adversarial review 93/100 (Pass, 2026-09-29)** — no blocking finding; full review at
`docs/qa/task-be-061-adversarial-review.md`. Residual (accepted): pilot low-bar identity trust
(OQ-001); session-locked identity (reconnect to switch account); route-split metric is a
non-blocking follow-up.

---

## TASK-BE-062 — PDF evidence path as a selectable `BssBillingPort` adapter

**Type:** Technical task (backend billing infrastructure) — ADR-0005 amended
**Status:** ✅ Merged into `feat/restart-from-scratch` (2026-09-30, `--no-ff` `5940dcb`) — backend **673** green + ArchUnit; adversarial 96/100 (Pass).
**Priority:** High
**Depends on:** TASK-BE-041 (`InvoicePdfExtractorPort` + `ExtractionResult`), TASK-BE-040/047 (`BssBillingPort`, structured JSON adapter), ADR-0004/0005
**Relates to:** OQ-003 (real BSS access), `missing-inputs.md` (`bill-run-documents/search` response gap)

### Context

The invoice-comparison engine already depends only on the outbound port `BssBillingPort`
(`listInvoices` + `fetchInvoice` → domain `Invoice`), with two implementations: `InMemoryBssBillingAdapter`
(mock fixtures) and `EirBssBillingAdapter` (real read-only **structured JSON** over the two Eir services).
A PDF extractor (`InvoicePdfExtractorPort`, ADR-0005) existed but was **wired to nothing** at runtime — the
PDF was framed as an inline "fallback seam". Requirement (2026-09-30): make PDF retrieval a **first-class,
selectable `BssBillingPort` implementation** so we can flip between "structured API → JSON" and "API →
PDF → parse → same structure" with a single config change, knowing the **real APIs can't be tested yet**.

### Decision / Implementation

1. **New outbound port `BillRunDocumentPort`** (`domain/port/out`): `listDocuments(account)` +
   `download(account, invoiceId) → Optional<PdfSource>` — the "fetch" half, mapping Galaxion
   `GET /bill-run-documents/search` and `GET /bill-run-documents/{id}/download`. Parsing stays in
   `InvoicePdfExtractorPort` (the two concerns remain separable).
2. **`PdfBssBillingAdapter implements BssBillingPort`**: `fetchInvoice` = download → `InvoicePdfExtractorPort.extract` → **regenerates the same domain `Invoice`** the JSON adapter returns. The LLM never reads the PDF (DEC-002). Fail-closed: empty download or `FAILED` extraction → `Optional.empty` (safe escalation, never a 500); `PARTIAL` still carries an invoice (confidence gate decides downstream); defense-in-depth **ownership check** drops a foreign-account invoice (BR-002-1). BSS network hop timed as its own slice (`provider=pdf`).
3. **Selection = one switch.** `VOICE_SUPPORT_BILLING_BSS_SOURCE` ∈ `{mock, eir, pdf}` in `BillingConfig`. The comparison/confidence/composer chain is **unchanged** whichever source is active.
4. **`FixtureBillRunDocumentAdapter`** (backed by the same in-memory fixtures) makes `source=pdf` exercisable **now**: the synthetic `PdfSource` carries the invoice **period id** as its reference (what `FixtureInvoicePdfExtractorAdapter` indexes on) + non-empty bytes.

### Acceptance (met)

- `source=pdf` runs the full download → extract → `Invoice` path over the fixtures; the billing route
  returns the same grounded comparison as `source=mock`. ✅
- Fail-closed branches locked (empty download, FAILED extraction, ownership mismatch) + PARTIAL kept. ✅
- Switching source is a single env change, no comparison-engine change. ✅
- Tests: `PdfBssBillingAdapterTest` (6), `FixtureBillRunDocumentAdapterTest` (5, incl. end-to-end
  download→fixture-extractor round-trip). Backend 673 + ArchUnit green. ✅
- ADR-0005 amended. ✅

### Out Of Scope / Deferred

- **Real REST `BillRunDocumentPort` adapter** (`RestBillRunDocumentAdapter`): blocked because
  `bill-run-documents/search` does **not** return period/amount (can't build `InvoiceSummary` from search
  alone — `missing-inputs.md`) and live access is unproven (OQ-003). When resolved, register it behind the
  same port + set the base URL; nothing else changes.
- **Real PDF parser** (PDFBox) behind `InvoicePdfExtractorPort` (`pdf.source=pdfbox`) — still fixture.

**Adversarial review 90/100 → 96/100 after remediation (Pass, 2026-09-30)** — no blocking finding; full
review at `docs/qa/task-be-062-adversarial-review.md`. Both non-blocking findings **fixed same session**:
(1) `PARTIAL` extraction now **fails closed** at the PDF adapter (BR-003 — never treat a partial parse as
complete); (2) **per-extraction telemetry** added — the BSS slice records a non-PII `reason`
(`document_unavailable`/`extraction_failed`/`extraction_partial`/`ownership_mismatch`). Backend 673 + ArchUnit
green. Residual: only the scope-deferred real REST adapter + real PDFBox parser (OQ-003). **The real REST
adapter is now implemented in TASK-BE-063 (gated off by default).**

---

## TASK-BE-063 — Real Galaxion `bill-run-documents` REST adapter (search + download)

**Type:** Technical task (backend billing infrastructure) — ADR-0005
**Status:** ✅ Merged into `feat/restart-from-scratch` (2026-10-01, `--no-ff`) — backend **691** green + ArchUnit; wired **off by default** (fixture stays active).
**Adversarial review 94/100 (Pass, 2026-10-01)** — no blocking finding; Residual (accepted): HTTP-mapping layer untested (consistent with the Eir REST adapters, no HTTP harness yet) + live tenant unproven (OQ-003). Full review: `docs/qa/task-be-063-adversarial-review.md`.
**Priority:** Medium
**Depends on:** TASK-BE-062 (`BillRunDocumentPort` + `PdfBssBillingAdapter`), TASK-BE-047 (Eir REST pattern)
**Relates to:** OQ-003 (real BSS access unproven), `missing-inputs.md` (`bill-run-documents/search` response gap)

### Context

TASK-BE-062 shipped the PDF evidence path as a selectable `BssBillingPort` adapter but left the **real**
`BillRunDocumentPort` implementation deferred — only `FixtureBillRunDocumentAdapter` existed. This task
implements the two real Galaxion `bill-run-documents` routes **now**, even though they are not called at
runtime yet (live access unproven, OQ-003), so the HTTP contract is in place and reviewed ahead of time.

### Decision / Implementation

1. **`BillRunDocumentClient` seam** (`adapter/out/bss/pdf`): `search(criteria, user) → List<BillRunDocument>`
   + `download(documentId, billPeriodId, user) → Optional<byte[]>`. Nested DTOs `DocumentSearchCriteria`
   (billRunAccountId / accountId / invoiceNumber / billPeriodId) and `BillRunDocument` (id / filename /
   contentType) — the only fields the search response carries. Mirrors the Eir `*Client` pattern.
2. **`RestBillRunDocumentAdapter implements BillRunDocumentClient`** (RestClient-backed, thin HTTP mapping,
   like `RestBillingEnquiryAdapter`): `GET /bill-run-documents/search` with the non-blank criteria as query
   params; `GET /bill-run-documents/{document_id}/download` returning `application/octet-stream` bytes. Both
   send the `galaxion-user-type` / `galaxion-user-identifier` headers; `404 → empty`, other errors propagate
   (sanitized 503 upstream).
3. **`GalaxionBillRunDocumentAdapter implements BillRunDocumentPort`** (uses the client; unit-tested with a
   fake): `download(account, invoiceId)` searches by `accountId + invoiceNumber`, takes the first non-blank
   document id, downloads the bytes and wraps them as `PdfSource(documentId, bytes)`. **Fail-closed**: no
   document, no bytes, or zero-length bytes → `Optional.empty`.
4. **`listDocuments` is BLOCKED by a contract gap** and fail-closes to an empty list: the
   `/bill-run-documents/search` response carries only id/filename/contentType — **no period, no amount** —
   so no `InvoiceSummary` (which needs period + TTC total) can be built from search alone (`missing-inputs.md`).
   It must not fabricate period/amount; comparable-invoice listing for `source=pdf` stays on a structured hop
   (`eir`) or waits for the search response to carry period/amount (OQ-003).
5. **Wiring = off by default.** `BillingConfig` wires `GalaxionBillRunDocumentAdapter` only when
   `voice-support.billing.bss.billrun.base-url` is set; blank (default) keeps `FixtureBillRunDocumentAdapter`,
   so the running `source=pdf` behaviour is unchanged and nothing is called at runtime yet.

### Acceptance (met)

- Both routes implemented with correct params/headers/octet-stream mapping. ✅
- `download` wired search→download with fail-closed branches; `listDocuments` documented + fail-closed. ✅
- Selection is a single config (`billrun.base-url`); default unchanged (fixtures). ✅
- Tests: `GalaxionBillRunDocumentAdapterTest` (6, via a fake client). Backend 691 + ArchUnit green. ✅

### Out Of Scope / Deferred

- **Live validation against the real Galaxion tenant** (OQ-003) — base URL unset until access is proven.
- **Real PDF parser** (PDFBox) behind `InvoicePdfExtractorPort` (`pdf.source=pdfbox`) — pairs with this
  adapter but stays fixture for now.
- **`listDocuments` real listing** — blocked until `search` carries period/amount (coordination request).
- **Observability**: the real adapter is not reachable at runtime (base URL unset), so no new slice is wired;
  when activated it sits under the existing `PdfBssBillingAdapter` BSS slice (`provider=pdf`). Not
  runtime-affecting until the base URL is set.

---

## TASK-BE-064 — Real invoice-PDF extractor (Apache PDFBox, `pdf.source=pdfbox`)

**Type:** Technical task (backend billing infrastructure) — ADR-0005 amended · new dependency (Apache PDFBox)
**Status:** 🔧 In review — backend **710** green + ArchUnit; selectable via `pdf.source=pdfbox`, **default stays fixture**. Branch `task/TASK-BE-064-pdfbox-extractor`.
**Adversarial review 94/100 (Pass, 2026-10-01)** — no blocking finding; a golden cross-check (`PdfFixtureEquivalenceTest`) proves the parser round-trips every synthetic (`BssBillingFixtures`) **and** real-transcribed (`EirB2cSampleFixtures`, 3 accounts) invoice to the same business data. Residual (accepted): the parser reads a synthetic labeled grammar, not the real eir B2C PDF layout, and the raw PDFs are held outside the repo — real-layout parsing + `parse(real eir PDF)==fixture` is the follow-up **TASK-BE-065** (OQ-003); mitigated by fixture-default (no live `pdfbox` path). Full review: `docs/qa/task-be-064-adversarial-review.md`.
**Priority:** Medium
**Depends on:** TASK-BE-041 (`InvoicePdfExtractorPort` + `ExtractionResult`), TASK-BE-062/063 (PDF path + document adapter)
**Relates to:** OQ-003 (real PDFs unproven), `invoice-extraction-json.md` (normalized contract)

### Context

The PDF evidence path (TASK-BE-062) and the real document adapter (TASK-BE-063) were in place, but the
`InvoicePdfExtractorPort` only had a **synthetic** fixture implementation — no real PDF was ever parsed. This
task implements the real extractor so the whole `bill-run-documents` → PDF bytes → `Invoice` chain can run on
real document bytes.

### Decision / Implementation

1. **Dependency:** Apache **PDFBox 3.0.5** (Apache-2.0, de-facto Java PDF library, actively maintained). Pinned
   in `pom.xml`; `commons-io` stays pinned at 2.19.0 in `dependencyManagement` so a PDFBox transitive cannot
   downgrade it (verified `dependency:tree`). Approved implicitly by the request (the project had no PDF-parsing
   capability — `jsoup`=HTML, `commons-csv`=CSV).
2. **`PdfBoxInvoiceExtractorAdapter implements InvoicePdfExtractorPort`** (`adapter/out/pdf`): `Loader.loadPDF`
   + `PDFTextStripper` turn the bytes into text (the real, deterministic PDF layer), then delegates to the
   parser. **Fail-closed**: empty document, corrupt/unreadable PDF or any parsing error → `ExtractionResult.failed`
   (never throws); the failure reason carries only the document reference + error type (no PDF content → no PII).
3. **`InvoiceTextParser`** (`infrastructure/pdf`, a pure parsing component outside `adapter.out` so the ArchUnit
   adapter-naming rule does not apply): parses a labeled grammar — `INVOICE / ACCOUNT / PERIOD / DATE / CURRENCY
   / LINE <category>|<label>|<amount> / VAT / TOTAL` — amounts to integer cents (comma/dot decimals + thousands
   separators). Status mirrors `invoice-extraction-json.md`: **FAILED** (unusable) when a required field is missing,
   **PARTIAL** when lines do not reconcile with the total, **SUCCESS** (parseable) when they reconcile. Unknown
   categories → `OTHER`; VAT split exposed at invoice level only (same stance as `EirBssBillingAdapter`).
4. **Selection = one switch.** `voice-support.billing.pdf.source` ∈ `{fixture, pdfbox}` in `BillingConfig`;
   default `fixture`, so local/pilot behaviour is unchanged until explicitly flipped.

### Acceptance (met)

- Real PDFBox text extraction + deterministic parse to the domain `Invoice`. ✅
- SUCCESS/PARTIAL/FAILED per the contract; fail-closed on empty/corrupt (never throws). ✅
- Single config switch; default fixture unchanged. ✅
- Tests: `InvoiceTextParserTest` (7, pure text) + `PdfBoxInvoiceExtractorAdapterTest` (3, real PDF round-trip
  via PDFBox + empty + corrupt) + `PdfFixtureEquivalenceTest` (2 golden cross-checks: every
  `BssBillingFixtures` **and** `EirB2cSampleFixtures` invoice rendered to a real PDF re-parses to the
  **same business data** — id, account, period, TTC/HT/VAT totals, per-line category+TTC; the no-line
  fixture → FAILED). Backend **710** + ArchUnit green. ✅
- ADR-0005 amended; PDFBox vetted + pinned. ✅

### Out Of Scope / Deferred

- **Grammar tuning to the real Galaxion PDF layout** — the labeled grammar is the stable contract; the exact
  label/section mapping is tuned when anonymized sample PDFs arrive (OQ-003).
- **Live activation** — `pdf.source` stays `fixture` by default; flip to `pdfbox` + pair with the real
  `bill-run-documents` base URL (TASK-BE-063) once real documents are available.
- **Observability**: `pdfbox` is not the default, so no runtime change; when active it runs under the existing
  `PdfBssBillingAdapter` BSS slice (`provider=pdf`) + per-extraction `reason`. Not runtime-affecting by default.

---

## TASK-BE-065 — Tune the PDF parser to the real eir B2C layout + validate against the sample PDFs

**Type:** Technical task (backend billing infrastructure) — follow-up of TASK-BE-064
**Status:** 📥 To do — **blocked on inputs** (raw anonymized eir B2C PDF bytes, held outside the repo — OQ-003)
**Priority:** Medium
**Depends on:** TASK-BE-064 (PDFBox extractor + synthetic grammar), TASK-BE-059 (`EirB2cSampleFixtures`, `eir-b2c-invoice-samples.md`)
**Relates to:** OQ-003, ADR-0005, ADR-0054

### Context

TASK-BE-064 ships a real PDFBox text layer + a deterministic parser, but the parser reads a **synthetic
labeled grammar** (`INVOICE/ACCOUNT/LINE a|b|c/VAT/TOTAL`), not the real eir B2C PDF layout. The three real
accounts (`99224964`, `99226126`, `99226337`) were **transcribed** from anonymized eir B2C PDFs into
`EirB2cSampleFixtures`, and `PdfFixtureEquivalenceTest` already proves the parser round-trips those fixtures
**semantically** — but through our own grammar renderer, not the real PDF layout. The raw PDFs are **held
outside the repo** (`eir-b2c-invoice-samples.md`: `…_EIR_MOBILE_TEST_…_B2C.pdf`), so we cannot yet prove
`parse(real eir PDF) == EirB2cSampleFixtures`.

### Scope

1. **Obtain the anonymized eir B2C sample PDFs** (coordination / `galaxion-coordination-request.md`) and
   commit them as test resources (or a sanitized equivalent) if licensing allows.
2. **Tune the parser to the eir B2C layout** (`eir-b2c-invoice-samples.md`): "at a glance" header + "Detail of
   your eir service" body, per-service **sections** (MSISDN/UAN + product), "Subscription and options for the
   period from X to Y" / "One-time charges and adjustments…" **groups** with subtotals, **negative discount
   lines**, **prorata line periods** (`from 25 Sep until 11 Oct`), and **invoice-level 23% VAT only** (G1).
   Preserve the ADR-0054 period model (usage vs monthly charge window, line periods).
3. **Golden validation:** `parse(real eir PDF) == EirB2cSampleFixtures` at full structural fidelity (sections,
   groups, line codes, periods, 23% VAT split), replacing/extending the current semantic round-trip.

### Acceptance

- The real eir B2C sample PDFs parse to the exact `EirB2cSampleFixtures` tree (ids, sections, groups, line
  codes/labels/periods, amounts, 23% VAT split, exact reconciliation).
- Deterministic, fail-closed, no PII in failure reasons (as TASK-BE-064).
- Closes the OQ-003 "real PDF layout" leg for eir B2C.

### Out Of Scope

- Non-eir Galaxion layouts; carry-forward / previous-balance (G3); consuming `chargePeriod` in the explanation
  composer (G4) — separate follow-ups.
