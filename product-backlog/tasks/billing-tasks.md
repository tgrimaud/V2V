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
D3c dedicated `POST /api/conversation/billing-explain`). **ADR-0051 Accepted.** Sub-tasks
1–8 done: `BillingIntentDetector` + `BillingExplanationComposer` + `ExplainBillingUseCase`
(billing core, 18 tests); `BillingExplanationPort`/`InProcBillingExplanationAdapter` seam +
`BillingAnswerService` + `POST /api/conversation/billing-explain` (10 tests);
`EscalationReason` += IDENTITY_UNVERIFIED/BILLING_UNEXPLAINED; BILLING OTel slice.
Full backend suite (560 tests) + ArchUnit green, Spring context boots. Adversarial review
**93/100** (QA gate: Pass). **Merge-ready** into `feat/sprint-14-billing-identity`
(`--no-ff`) — awaiting explicit merge request.
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
follow-up). Next: write **ADR-0051**, then implement the 9 sub-tasks (full target flow +
escalation + mandatory OTel slice + sub-tasks in the cadrage doc).

## Proposed (later this sprint — full sections created when picked up)

| Ticket | Title | Gate |
|--------|-------|------|
| TASK-BE-046 | Billing KB entries for confirmed causes | — |
| TASK-QA-019 | Billing fixtures + Gherkin/Behave journeys + latency slices | 1–8 |
| TASK-BE-047 | Real Galaxion read-only adapter behind `BssBillingPort` | OQ-003 |
| TASK-QA-020 | Real-data validation on provided anonymized PDFs/payloads | real data |
| TASK-INFRA-017 | Galaxion inputs coordination package (`galaxion-coordination-request.md`) | — (drafted) |
