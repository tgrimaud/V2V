# Sprint 14 — Billing Identity + BSS/PDF Evidence + Deterministic Comparison

## Sprint Objective

Prove the **billing value** of the bot: a customer is identified with enough
confidence, the bot retrieves billing evidence (invoices/periods), a **deterministic
engine** computes what changed between two invoices and **why** (business causes), and
only then the LLM formulates a **grounded** explanation — the LLM never computes or
guesses amounts (ADR-0003/0005, DEC-002).

This sprint sits **behind** the existing KB-grounded answer engine (Sprint 7) and the
voice/Genesys transports (Sprints 6/12/13). It adds the billing domain, the BSS access
port, the PDF-evidence path and the comparison engine — **without** moving any billing
logic into Genesys or letting the LLM read a PDF to calculate.

**Design invariant (enforced at review):** amounts and causes are calculated by
deterministic code **before** any LLM wording; the LLM only phrases confirmed, traceable
evidence. BSS access is **read-only** in V1 (ADR-0003). The billing source of truth is the
BSS; the PDF is the invoice-detail evidence path until a validated structured
invoice-line endpoint exists (ADR-0005).

## Strategy — seams-first, fixture-driven (build now, swap real data when it lands)

Per `docs/integrations/galaxion/missing-inputs.md` (§"What Can Move Forward Without These
Inputs"), the sprint is structured so the **engine is buildable and fully testable today
against fixtures and a BSS mock**, while the **real Galaxion adapter, the real customer
identity source, and real anonymized PDFs are a later swap** gated by the three open
questions below. This mirrors the Sprint 12/13 "reusable seams" pattern: the typed
`BssBillingPort` (ADR-0004) and the extraction/comparison contracts are the seam; the real
Galaxion REST/PDF adapter drops in behind them without touching the domain.

Consequence: **most of the sprint can start without the OQ answers** (domain model,
port + use cases, BSS mock, PDF extractor on synthetic PDFs, comparison engine, fixtures,
QA journeys). What the OQs gate is the **real-data validation** and **go-live** portion
(real identity, real BSS granularity, real PDF extraction quality).

## Gating Open Questions (decision owners)

After the 2026-09-08 scoping decision, **OQ-001 is deferred** (pilot uses known/manual
identity) and **OQ-003/OQ-004 are answered as the committed real data arrives** — they gate
**real-data acceptance**, not the fixture-driven build.

| OQ | Question | Owner | Status for this sprint |
|----|----------|-------|-------|
| **OQ-001** | How is the customer identity established on phone (Genesys IVR/ANI) and web voice, and the minimum confidence for invoice access? | Product / BSS / Security | **Deferred** — pilot ships known/manual identity behind the port; real source a later increment |
| **OQ-003** | Which BSS data is available read-only, at what granularity/history/freshness, and can a structured invoice-line endpoint later replace PDF? | BSS owner | **Answered as data arrives** — gates the real Galaxion adapter granularity (US-005, BE-047) |
| **OQ-004** | Which real anonymized invoice PDFs + extraction-quality thresholds validate V1 behaviour (parseable/partial/unusable)? | Product / BSS / QA | **Answered as data arrives** — gates real PDF extraction acceptance (US-008, QA-020) |

Sub-decisions to record are enumerated in `product-backlog/open-questions/v1-open-questions.md`
(OQ-001/003/004) and requested in `docs/integrations/galaxion/missing-inputs.md`.
**OQ-002** (minimum proof threshold before answering vs escalating) also applies to the
explanation gate; a provisional three-band confidence policy exists (ADR-0034) pending it.

### Scoping decisions (user, 2026-09-08)

Stakeholder-stated premises that shaped the scope below:

- **Start now on the fixtures/mock build**, resolving real data in parallel — the sprint
  is not held for the OQ answers.
- **Pilot identity mode = known/manual** (pilot testers with a known account) behind the
  identity port; the **real Genesys IVR/ANI source is deferred** to a later increment
  (OQ-001 sub-decision recorded when it lands).
- **Real anonymized Galaxion PDFs + BSS payloads will be provided** during the sprint —
  so the **real Galaxion read-only adapter + real-data validation are IN scope** (they
  still land behind `BssBillingPort`, mock kept for tests, read-only per ADR-0003). OQ-003
  (granularity/access) and OQ-004 (extraction-quality threshold) sub-decisions are
  answered as the data arrives; INFRA-017 tracks the delivery.

## In Scope

- **Customer identity resolution** with a confidence level per pilot channel, and a
  fail-safe (clarify or escalate) when identity is insufficient (US-004, EPIC-002).
- **Billing evidence retrieval** through a typed read-only `BssBillingPort` — invoices,
  periods, and the metadata to select two comparable periods (US-005, ADR-0004).
- **Insufficient-evidence detection** before any explanation (US-006).
- **BSS mock + static fixtures** (`customer-eir-001…006`) covering the V1 journeys
  (US-007).
- **Invoice PDF → structured JSON extraction** on synthetic (non-Galaxion) PDFs, with an
  explicit extraction status `parseable` / `partial` / `unusable` (US-008, ADR-0005).
- **Deterministic comparison engine**: select two periods, diff lines
  (appeared/disappeared/changed), attribute business causes (discount expiry, overage,
  option change, proration, one-off fee, adjustment, tax, unexplained), order by impact,
  and **expose unreconciled amounts** rather than hide them (US-010/011/012/013,
  EPIC-004).
- **Grounded billing explanation**: the answer engine phrases the deterministic result;
  the LLM never computes amounts (US-012, DEC-002).
- **Billing KB entries** for the confirmed causes' tariff/business wording (US-009).
- **Real Galaxion read-only adapter** behind `BssBillingPort` + **real-data validation**
  against the provided anonymized PDFs/payloads (per the 2026-09-08 decision) — the mock
  stays for tests; access stays read-only (ADR-0003/0004). Gated on OQ-003 granularity.
- **Per-step observability** (identity → BSS fetch → PDF extract → comparison → wording)
  with correlation id and sanitized errors (mandatory runtime instrumentation).
- **Galaxion inputs coordination package** to obtain the real PDFs/payloads + confirm
  OQ-001/003/004 sub-decisions (mirrors the Sprint 13 admin-coordination pattern).

## Out Of Scope

- **Real Genesys IVR/ANI identity integration** — deferred; the pilot uses known/manual
  identity behind the identity port (2026-09-08 decision, OQ-001 later).
- **Write access / any BSS mutation** — V1 is read-only (ADR-0003, BR-002-2). *(The real
  Galaxion read-only adapter itself is now IN scope — see In Scope.)*
- **LLM reading the PDF to compute amounts** — forbidden (BR-003-1).
- **Domains beyond billing** (technical support, sales, retention) — the architecture
  stays extensible but V1 remains invoice explanation.
- **Genesys live-org validation + latency workstream** — parallel tracks (OQ-006,
  TASK-WEB-044, TASK-BE-033/STT-014/BE-020), not this sprint.
- **Final proof-threshold policy** (OQ-002) — provisional bands (ADR-0034) stay until the
  decision lands.

## Business Rules (traceability)

| ID | Rule | Source |
|----|------|--------|
| BR-002-1 | Explain invoices only for a customer identified with enough confidence | EPIC-002 |
| BR-002-2 | BSS access is read-only in V1 | EPIC-002 / ADR-0003 |
| BR-002-3 | Insufficient identity/evidence → clarify or escalate (never invent) | EPIC-002 |
| BR-003-1 | The LLM never reads an invoice PDF to calculate amounts | EPIC-003 / ADR-0005 |
| BR-003-2 | Partial/unusable extraction never yields confirmed unsupported amounts | EPIC-003 |
| BR-003-3 | Fixtures demonstrate reliable explanation **or** safe limitation/escalation | EPIC-003 |
| BR-004-1 | Amounts and causes are calculated **before** LLM wording | EPIC-004 |
| BR-004-2 | The global delta is explained by traceable causes or declared incomplete | EPIC-004 |
| BR-004-3 | Causes are ordered by decreasing impact when amounts are available | EPIC-004 |

## Tickets (proposed — to confirm/mint at sprint start)

> IDs are **proposed** and must be grepped across all branches before minting (per the
> ID-collision rule). Full ticket sections are created at sprint start on the sprint
> branch. Every ticket is **conditional**: the fixture-buildable ones can start now; the
> real-data ones are gated by the OQ noted.

| # | Ticket (proposed) | Title | Role | Gate | US / Rule |
|---|---|---|---|---|---|
| 1 | TASK-BE-038 | **Billing domain model** — `Invoice`, `InvoiceLine`, `InvoiceComparison`, `BillingCause`, `Evidence` (pure domain, no Spring); **mirror the real BSS `invoice → section → group → item` hierarchy** with amounts at each level (`bss-billing-data-model.md`) | Build (backend domain) | — (fixtures) | EPIC-004 / ADR-0003 |
| 2 | TASK-BE-039 | **`BssBillingPort` + use cases** — typed read-only business port for invoices/periods (no live adapter) | Build (backend port) | — (fixtures) | US-005 / ADR-0004 |
| 3 | TASK-BE-040 | **BSS mock adapter + static fixtures** `customer-eir-001…006` (nominal, discount expiry, overage, proration, insufficient, unusable) | Build (backend adapter + fixtures) | — (fixtures) | US-005/007 / BR-003-3 |
| 4 | TASK-BE-041 | **Invoice PDF extractor → structured JSON** on synthetic PDFs; extraction status `parseable`/`partial`/`unusable` | Build (backend) | — (synthetic) | US-008 / ADR-0005 / BR-003-1/2 |
| 5 | TASK-BE-042 | **Deterministic comparison engine** — period selection + line diff (appeared/disappeared/changed at `invoice_item` level) + business-cause attribution (from `type`/`code`/`vatType`, needs the BSS code catalogue) + roll-up reconciliation (item→group→section→invoice) + unreconciled exposure, ordered by impact | Build (backend domain) | — (fixtures) | US-010/011/012/013 / BR-004-1/2/3 |
| 6 | TASK-BE-043 | **Evidence-sufficiency / confidence gate** before explanation (insufficient → clarify/escalate) | Build (backend) | OQ-002 (provisional) | US-006 / BR-002-3 |
| 7 | TASK-BE-044 | **Customer identity resolution (pilot mode)** — identity + confidence + fail-safe; pilot uses known/manual context while the real source is gated | Build (backend) + ADR | **OQ-001** | US-004 / BR-002-1 |
| 8 | TASK-BE-045 | **Wire the billing chain behind the answer engine** — grounded explanation from the deterministic result (LLM phrases only) | Build (backend integration) | 1–6 | US-012 / DEC-002 / BR-004-1 |
| 9 | TASK-BE-046 | **Billing KB entries** for confirmed causes' tariff/business wording (reviewed) | Build (KB content) | — | US-009 |
| 10 | TASK-QA-019 | **Billing fixtures + Gherkin/Behave journeys** — nominal, discount expiry, overage, proration, insufficient, partial/unusable + latency slices | QA | 1–8 | US-007 / all AC |
| 11 | TASK-INFRA-017 | **Galaxion inputs coordination package** — obtain real anonymized PDFs + `bill-run-documents` payloads + confirm identity/granularity/threshold rules (**request doc drafted:** `docs/integrations/galaxion/galaxion-coordination-request.md`) | Doc / coordination | — | OQ-001/003/004 |
| 12 | TASK-BE-047 | **Real Galaxion read-only adapter** behind `BssBillingPort` (REST + PDF retrieval via `bill-run-documents`) — **in scope** per 2026-09-08 decision | Build (backend adapter) | **OQ-003** | US-005 / ADR-0004 |
| 13 | TASK-QA-020 | **Real-data validation** — run the extractor + comparison engine on the provided anonymized PDFs/payloads; confirm extraction-quality threshold (OQ-004) and reconciliation on real invoices | QA | 4,5,12 + real data | US-008/011 / BR-003-2 |

Full ticket details will live in `tasks/backend-hardening-tasks.md` (BE),
`tasks/backend-hardening-tasks.md`/`tasks/kb-ingestion-tasks.md` (KB), and
`tasks/deployment-tasks.md` (INFRA-017) once the sprint starts.

## Dependencies & Sequencing

```
OQ-001 (identity, later) ─┐                  OQ-003 (BSS granularity) ─┐   OQ-004 (real PDFs) ─┐
                          ▼                                            ▼                       ▼
   TASK-BE-044 (identity, pilot manual)        TASK-BE-047 (real Galaxion adapter)   QA-020 real-data validation
                   │                                                   │                       │
                   ▼                                                   ▼                       ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────────┐
  │  Fixture-buildable now (no OQ blocker):                                                       │
  │  BE-038 (domain) ─▶ BE-039 (port) ─▶ BE-040 (mock+fixtures)                                   │
  │                     BE-041 (PDF extractor, synthetic) ─┐                                      │
  │                     BE-042 (comparison engine) ────────┼─▶ BE-045 (wire behind answer engine) │
  │                     BE-043 (evidence gate) ────────────┘        ▲                             │
  │                     BE-046 (billing KB) ───────────────────────┘                             │
  │  QA-019 (fixtures + journeys) covers all of the above                                        │
  └────────────────────────────────────────────────────────────────────────────────────────────┘
  INFRA-017 (Galaxion inputs request) runs in parallel to resolve OQ-001/003/004 for real-data acceptance.
```

- **Domain (BE-038) is the spine**; the port (BE-039) and mock (BE-040) make everything
  testable without the BSS. The comparison engine (BE-042) is the core value.
- **BE-045** (wire behind the answer engine) integrates last, once the deterministic
  result exists — the LLM only phrases it.
- **BE-047 (real adapter) + QA-020 (real-data validation)** are in scope (real data
  committed 2026-09-08), running in parallel behind the port; **INFRA-017** delivers the
  data. If the data slips, they carry forward and the sprint still closes on fixtures/mock.

## Observability & latency expectations (ADR-0028 / ADR-0029)

- **Per-step billing slices** reported p50/p95: identity resolution, BSS fetch, PDF
  extraction, comparison, wording. Un-instrumented steps are emitted `measured=false` with
  a reason (US-036 rule), never omitted.
- **Correlation id** propagated across the billing chain into one trace (same approach as
  the voice→backend deterministic `traceparent`).
- **Sanitized errors** — no PII (account ids, amounts tied to identity) in logs/traces;
  masking rules follow OQ-001's confidentiality decisions.
- No new voice-path SLO is claimed here; the billing steps are added to the existing
  latency taxonomy.

## Risks & Degraded Modes

| Risk / failure mode | Design response (this sprint) |
|---|---|
| Real anonymized PDFs unavailable in the sprint window | Build on **synthetic** PDFs + fixtures; real-PDF acceptance carried forward (OQ-004 / INFRA-017) |
| BSS read-only access not granted | Stay on the **BSS mock** behind `BssBillingPort`; real adapter is a later swap (OQ-003) |
| Identity source undecided for the pilot | **Pilot identity mode** (known/manual context) behind the identity port; real source gated (OQ-001) — escalate if it blocks pilot calls |
| Extraction partial/unusable | Separate confirmed from uncertain; never present unsupported amounts as confirmed (BR-003-2) |
| Delta not fully reconciled | **Expose the unreconciled amount** + declare the explanation incomplete (BR-004-2) |
| Insufficient evidence/identity | Clarify or escalate to a human advisor with context (BR-002-3, ties to ADR-0019 handoff) |

## Exit Criteria / Definition of Done

**Always required:**

- The **deterministic comparison engine** turns two fixture invoices into line diffs +
  ordered business causes + a reconciliation result (with unreconciled amounts exposed),
  fully unit-tested on the `customer-eir-001…006` fixtures (US-010/011/012/013).
- The **PDF extractor** produces structured JSON with a `parseable`/`partial`/`unusable`
  status on synthetic PDFs; partial/unusable never yields confirmed amounts (US-008).
- The **evidence/identity fail-safe** clarifies or escalates instead of inventing an
  explanation (US-004/006).
- The answer engine phrases a **grounded** explanation from the deterministic result; the
  LLM computes nothing (US-012, DEC-002) — locked by a regression test.
- **QA journeys** (nominal, discount expiry, overage, proration, insufficient,
  partial/unusable) pass as Gherkin/Behave (US-007); per-step latency slices reported.
- Observability (per-step slices + correlation id + sanitized errors) present or the story
  is marked not-runtime-affecting.
**Real-data acceptance (in scope per the 2026-09-08 decision; carries forward only if the data slips):**

- The **real Galaxion read-only adapter** retrieves invoices/PDFs behind `BssBillingPort`
  at the confirmed granularity (OQ-003), mock kept for tests (BE-047).
- The extractor + comparison engine run on the **provided anonymized real PDFs/payloads**,
  meeting the agreed extraction-quality threshold (OQ-004), with reconciliation validated
  on real invoices (QA-020).
- OQ-003/004 sub-decisions are **recorded** as the data arrives; INFRA-017 tracks delivery.

**Deferred (recorded, not this sprint):**

- Real **Genesys IVR/ANI** identity source (OQ-001) — the pilot ships known/manual identity
  behind the identity port.

## Traceability

- **EPICs:** EPIC-002 (identity + evidence), EPIC-003 (BSS/PDF fixtures + extraction),
  EPIC-004 (deterministic comparison), EPIC-005 (answer engine, reused).
- **User stories:** US-004…013.
- **ADRs:** ADR-0003 (read-only BSS + deterministic comparison), ADR-0004 (typed BSS
  ports), ADR-0005 (PDF extraction before LLM), ADR-0034 (provisional confidence bands);
  **new ADR expected** for the pilot customer-identity source + confidence model
  (proposed ADR-0050, pending OQ-001).
- **Decisions:** DEC-002 (grounding — LLM phrases only).
- **Open questions:** OQ-001, OQ-002, OQ-003, OQ-004.
- **Integration docs:** `docs/integrations/galaxion/{bss-billing-data-model,bss-integration-plan,galaxion-billing-contracts,invoice-extraction-json,missing-inputs}.md`
  — the **real BSS billing data model** (2026-09-08) grounds the domain model (BE-038)
  and comparison engine (BE-042), and raises a structured-source-vs-PDF option (OQ-003).

## Sprint Branch

Not created yet. At sprint start, fork `feat/sprint-14-billing-identity` from
`feat/restart-from-scratch`; ticket branches fork from and merge back into the sprint
branch (`git merge --no-ff`); the sprint branch merges into `feat/restart-from-scratch`
only at closure on the user's explicit request (two-level model).

## Status

**Status:** 📋 **Planned — ready to start** — scoping decided 2026-09-08: start now on the
fixtures/mock build; **pilot identity = known/manual** (real Genesys IVR/ANI deferred,
OQ-001); **real Galaxion read-only adapter + real-data validation IN scope** (real
anonymized PDFs/payloads to be provided — OQ-003/004 answered as data arrives, tracked by
INFRA-017). Resequenced from Sprint 12 → 14 on 2026-08-15. File prepared 2026-09-08.
