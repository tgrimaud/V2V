# V1 Epics - From-Scratch Restart

## Restart Context

This branch restarts implementation from scratch. The previous implementation
remains preserved on `main` as a backup and reference, but the V1 backlog below
is written as if no delivery code exists yet.

The product outcome remains unchanged: explain operator invoice deltas with
read-only BSS/PDF evidence, deterministic comparison before LLM wording,
Voice2Voice access, Genesys advisor handoff, and measurable pilot latency.

## Epic Map

| Epic | Classification | Status | Governing references |
|---|---|---|---|
| EPIC-001 Product and architecture baseline | V1 foundation | Draft | ADR-0017, ADR-0020, OQ-001, OQ-006 |
| EPIC-002 Customer identity and billing evidence access | V1 core | Draft | ADR-0003, ADR-0004, OQ-001, OQ-003 |
| EPIC-003 BSS/PDF fixture and extraction path | V1 enabler | Draft | ADR-0005, OQ-004, Galaxion docs |
| EPIC-004 Deterministic invoice comparison | V1 core | Draft | ADR-0003, ADR-0005 |
| EPIC-005 Evidence-backed explanation engine | V1 core | Draft | ADR-0003, ADR-0017 |
| EPIC-006 Voice2Voice journey foundation | V1 core | Draft | ADR-0002, ADR-0011, ADR-0018 |
| EPIC-007 Genesys advisor handoff | V1 core | Draft | ADR-0019, ADR-0020, OQ-006 |
| EPIC-008 Web synthesis and evidence view | V1 enabler | Draft | ADR-0003, ADR-0017 |
| EPIC-009 Trust, security and auditability | V1 enabler | Draft | ADR-0003, ADR-0008, OQ-001 |
| EPIC-010 Observability, latency and pilot validation | V1 pilot gate | Draft | ADR-0010, ADR-0018, OQ-005, OQ-006 |

---

## EPIC-001 - Product And Architecture Baseline

**Status:** Draft
**Priority:** High
**Classification:** V1 foundation

### Goal

The team starts from a shared V1 target, delivery sequence, architectural
boundaries and open-question register before writing new code.

### Scope

- Reconfirm the V1 value slice: invoice delta explanation for operator end users.
- Preserve the boundary that billing logic, RAG, guardrails and escalation policy
  belong to the backend, while the voice runtime owns real-time media.
- Preserve the Genesys target pattern: Genesys is the contact-center system of
  record; the bot backend owns conversation intelligence and handoff content.
- Define delivery slices small enough to build and validate from an empty codebase.

### Business Rules

| ID | Rule |
|----|------|
| BR-001-1 | No implementation story starts until its product-visible acceptance criteria are explicit. |
| BR-001-2 | The previous implementation may inform decisions, but it is not treated as reusable code on this branch. |
| BR-001-3 | Any missing product, BSS, security or Genesys input is recorded as an open question. |

### User Stories

- US-001 - Reconfirm the V1 restart baseline.
- US-002 - Define the delivery sequence for the empty codebase.
- US-003 - Confirm the channel and identity boundary.

---

## EPIC-002 - Customer Identity And Billing Evidence Access

**Status:** Draft
**Priority:** High
**Classification:** V1 core

### Goal

The bot can determine which customer account is in scope and retrieve enough
billing evidence to decide whether an invoice explanation is allowed.

### Scope

- Establish the customer identity and confidence level for each pilot channel.
- Reuse Genesys IVR, ANI or contact-center lookup context when Genesys is the
  phone entry point.
- Retrieve invoices, periods and billing context from the BSS source of truth.
- Detect missing, insufficient or unauthorized evidence before any explanation.

### Business Rules

| ID | Rule |
|----|------|
| BR-002-1 | The bot explains invoices only for a customer identified with enough confidence. |
| BR-002-2 | BSS access is read-only in V1. |
| BR-002-3 | If identity or evidence is insufficient, the bot asks for clarification or escalates. |

### User Stories

- US-004 - Identify the customer at the start of the exchange.
- US-005 - Retrieve available invoices and billing periods.
- US-006 - Detect insufficient BSS evidence.

### Open Questions

- OQ-001 - Customer identification by phone and web voice channel.
- OQ-003 - BSS data availability and granularity.

---

## EPIC-003 - BSS/PDF Fixture And Extraction Path

**Status:** Draft
**Priority:** High
**Classification:** V1 enabler

### Goal

The team can validate billing behavior with realistic fixtures before full BSS
sandbox access and structured invoice-line endpoints are stable.

### Scope

- Define realistic fixture journeys: nominal, discount expiry, overage,
  proration, insufficient data and unreliable extraction.
- Extract invoice PDFs into deterministic structured evidence when no validated
  structured line endpoint exists.
- Represent extraction status as `parseable`, `partial` or `unusable`.
- Keep fixture evidence readable by Product, Billing, QA and Engineering.

### Business Rules

| ID | Rule |
|----|------|
| BR-003-1 | The LLM never reads an invoice PDF to calculate amounts. |
| BR-003-2 | Partial or unusable extraction never leads to confirmed unsupported amounts. |
| BR-003-3 | Fixtures must demonstrate either reliable explanation or safe limitation/escalation. |

### User Stories

- US-007 - Use realistic BSS/PDF fixtures for V1 validation.
- US-008 - Handle invoice extraction status.
- US-009 - Validate billing and pricing knowledge for V1.

### Open Questions

- OQ-004 - Invoice PDF extraction reliability and fixture coverage.

---

## EPIC-004 - Deterministic Invoice Comparison

**Status:** Draft
**Priority:** High
**Classification:** V1 core

### Goal

The system identifies invoice deltas and business causes deterministically before
any LLM wording.

### Scope

- Select two invoices or billing periods to compare.
- Identify lines that appeared, disappeared or changed.
- Identify business causes such as discount expiry, usage overage, option change,
  proration, one-off fee, adjustment, tax or unexplained amount.
- Expose unreconciled amounts instead of hiding them.

### Business Rules

| ID | Rule |
|----|------|
| BR-004-1 | Amounts and causes are calculated before LLM wording. |
| BR-004-2 | The global delta must be explained by traceable causes or declared incomplete. |
| BR-004-3 | Causes are ordered by decreasing impact when amounts are available. |

### User Stories

- US-010 - Select two invoices or billing periods to compare.
- US-011 - Identify changed invoice lines and amounts.
- US-012 - Identify the main business causes.
- US-013 - Expose unresolved or unreconciled amounts.

---

## EPIC-005 - Evidence-Backed Explanation Engine

**Status:** Draft
**Priority:** High
**Classification:** V1 core

### Goal

The customer receives a clear oral explanation backed by billing evidence and
approved billing knowledge.

### Scope

- Produce a concise synthesis that starts with the total delta.
- Link every confirmed cause to evidence.
- Explain relevant billing rules from the knowledge base.
- Refuse to conclude when available proof is insufficient.

### Business Rules

| ID | Rule |
|----|------|
| BR-005-1 | Every explanation is tied to evidence or explicitly states what is missing. |
| BR-005-2 | The knowledge base explains rules but never replaces BSS facts. |
| BR-005-3 | The bot must not invent causes, amounts or certainty. |

### User Stories

- US-014 - Receive a synthesis of increase or decrease causes.
- US-015 - Obtain evidence for each cause.
- US-016 - Explain the billing rule behind a delta.
- US-017 - Disclose when no reliable explanation can be produced.

### Open Questions

- OQ-002 - Minimum proof threshold for answering without escalation.

---

## EPIC-006 - Voice2Voice Journey Foundation

**Status:** Draft
**Priority:** High
**Classification:** V1 core

### Goal

A customer can ask a billing question orally and receive a spoken acknowledgement,
answer or escalation path with acceptable perceived latency.

### Scope

- Deliver phone Voice2Voice and web Voice2Voice journeys.
- Provide a quick spoken acknowledgement when evidence analysis takes time.
- Handle turn detection and barge-in as product-visible voice behavior.
- Keep the voice provider replaceable behind the target architecture.

### Business Rules

| ID | Rule |
|----|------|
| BR-006-1 | Voice2Voice is mandatory in V1. |
| BR-006-2 | Speed must not override billing correctness. |
| BR-006-3 | The customer can ask for a human advisor at any time. |

### User Stories

- US-018 - Call the bot for a spoken invoice explanation.
- US-019 - Ask from a web voice chat.
- US-020 - Receive a quick spoken acknowledgement during long analysis.
- US-021 - Interrupt the bot during a spoken answer.
- US-022 - Use text to complement a voice question.
- US-041 - End the call when the customer signals they are done.

---

## EPIC-007 - Genesys Advisor Handoff

**Status:** Draft
**Priority:** High
**Classification:** V1 core

### Goal

The customer is transferred or prepared for transfer through Genesys when they ask
for a human advisor or when the bot cannot answer safely.

### Scope

- Detect explicit advisor requests.
- Detect insufficient evidence, unusable extraction or unresolved deltas.
- Prepare a Genesys-compatible advisor context.
- Keep full Genesys voice routing separate from mandatory V1 handoff unless the
  pilot environment requires it.

### Business Rules

| ID | Rule |
|----|------|
| BR-007-1 | Every explicit advisor request triggers the handoff path. |
| BR-007-2 | The bot escalates when it lacks enough proof to explain the delta. |
| BR-007-3 | Genesys remains the contact-center system of record. |
| BR-007-4 | The backend owns escalation policy and handoff content. |

### User Stories

- US-023 - Be transferred on explicit request.
- US-024 - Be transferred when the bot lacks enough certainty.
- US-025 - Provide the advisor with usable context.
- US-026 - Hand off to Genesys with advisor context.
- US-027 - Validate whether full Genesys voice routing is required for the pilot.

### Open Questions

- OQ-006 - Genesys handoff integration shape.

---

## EPIC-008 - Web Synthesis And Evidence View

**Status:** Draft
**Priority:** Medium
**Classification:** V1 enabler

### Goal

The web journey can show the customer or advisor the same explanation, limits and
evidence that were used in the spoken answer.

### Scope

- Display the global delta.
- Display main causes and their contribution.
- Display line-by-line differences when safe and available.
- Display evidence, unresolved points and analysis limits.

### User Stories

- US-028 - Read the synthesis on the web page.
- US-029 - Consult the global delta.
- US-030 - Consult cause details.
- US-031 - See evidence and analysis limits.
- US-032 - Consult line-by-line invoice differences.

---

## EPIC-009 - Trust, Security And Auditability

**Status:** Draft
**Priority:** High
**Classification:** V1 enabler

### Goal

The bot handles sensitive billing data safely and leaves enough traceability for
support, audit and dispute handling.

### Scope

- Limit exposed personal and billing data.
- Keep BSS access read-only.
- Audit sensitive consultations and escalation outcomes.
- Make analysis limits visible to the customer and advisor.

### User Stories

- US-033 - Protect personal data exposed to the customer.
- US-034 - Audit sensitive consultations.
- US-035 - Disclose analysis limits.

---

## EPIC-010 - Observability, Latency And Pilot Validation

**Status:** Draft
**Priority:** High
**Classification:** V1 pilot gate

### Goal

The team can validate pilot readiness, explain failures, and identify which
component contributes to latency before making any production SLO claim.

### Scope

- Measure voice timing by pipeline slice: channel ingress, end-of-turn, STT,
  backend first token or action, BSS/PDF evidence, comparison, RAG, LLM, TTS,
  channel egress and Genesys handoff.
- Correlate participating components with a shared correlation id.
- Combine Genesys contact-center metrics with AI-layer metrics.
- Track escalations, unresolved questions and pilot go/no-go evidence.

### Business Rules

| ID | Rule |
|----|------|
| BR-010-1 | End-to-end latency alone is not enough for pilot acceptance. |
| BR-010-2 | Pilot reports must publish p50, p95, p99, sample size, channel and warm/cold state. |
| BR-010-3 | Production SLOs remain unclaimed until degraded modes and observability are proven. |

### User Stories

- US-036 - Measure key voice journey timings by pipeline slice.
- US-037 - Measure invoice comparison response time.
- US-038 - Track escalations and their reasons.
- US-039 - Track unresolved questions.
- US-040 - Produce the pilot readiness report.

### Open Questions

- OQ-005 - Pilot latency acceptance context.
