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

## Proposed (later this sprint — full sections created when picked up)

| Ticket | Title | Gate |
|--------|-------|------|
| TASK-BE-041 | Invoice PDF extractor → structured JSON (synthetic) + extraction status | fixtures |
| TASK-BE-043 | Evidence-sufficiency / confidence gate before explanation | OQ-002 (provisional) |
| TASK-BE-044 | Customer identity resolution (pilot mode) + ADR-0050 | OQ-001 (pilot) |
| TASK-BE-045 | Wire billing chain behind the answer engine (grounded, LLM phrases only) | 1–6 |
| TASK-BE-046 | Billing KB entries for confirmed causes | — |
| TASK-QA-019 | Billing fixtures + Gherkin/Behave journeys + latency slices | 1–8 |
| TASK-BE-047 | Real Galaxion read-only adapter behind `BssBillingPort` | OQ-003 |
| TASK-QA-020 | Real-data validation on provided anonymized PDFs/payloads | real data |
| TASK-INFRA-017 | Galaxion inputs coordination package (`galaxion-coordination-request.md`) | — (drafted) |
