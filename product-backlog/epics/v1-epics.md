# V1 Epics - Invoice Explanation Voice Assistant

## Epic Map

The V1 backlog is organized around the canonical product outcome: explain invoice
deltas with read-only BSS/PDF evidence through phone and web Voice2Voice journeys.

| Epic | Classification | Governing references |
|---|---|---|
| EPIC-001 Customer and billing context | V1 core | ADR-0003, ADR-0004, OQ-001, OQ-003 |
| EPIC-002 Invoice comparison | V1 core | ADR-0003, ADR-0005 |
| EPIC-003 Evidence-backed explanation | V1 core | ADR-0003, ADR-0005, ADR-0017 |
| EPIC-004 Phone Voice2Voice | V1 core | ADR-0002, ADR-0011, ADR-0018 |
| EPIC-005 Web Voice2Voice | V1 core | ADR-0002, ADR-0011, ADR-0018 |
| EPIC-006 Human escalation | V1 core | ADR-0019, ADR-0020 |
| EPIC-007 Web synthesis and evidence | V1 enabler | ADR-0003, ADR-0017 |
| EPIC-008 Trust, security and audit | V1 enabler | ADR-0003, ADR-0008, OQ-001 |
| EPIC-009 Quality and performance measurement | V1 pilot gate | ADR-0010, ADR-0018, OQ-005, OQ-006 |
| EPIC-010 BSS/PDF evidence fixture path | V1 enabler | ADR-0004, ADR-0005, Galaxion docs |

---

## EPIC-001 - Identify The Customer And Retrieve Billing Context

**Status:** Ready for review  
**Priority:** High  
**Classification:** V1 core

### Goal

The bot knows which customer account the request concerns and has enough billing
context before explaining a price difference.

### Scope

- Identify the customer from the activation channel or pilot-provided context.
- Reuse Genesys IVR, ANI or contact-center lookup context when Genesys is the
  phone entry point.
- Retrieve invoices, periods and useful billing context from the BSS source of
  truth.
- Detect cases where identity, invoice access or billing data is insufficient.

### V1 Delivery Slice

- Accept a trusted customer context supplied by the channel, pilot fixture or BSS.
- Retrieve at least two comparable billing periods for an identified customer.
- Block or escalate the explanation when identity, periods or minimum evidence
  are not reliable.

### Out Of Scope

- Full customer enrollment.
- Final target strong-authentication design beyond the pilot trust model.
- Any BSS write action or invoice correction.

### Business Rules

| ID | Rule |
|----|------|
| BR-001-1 | The bot explains invoices only for a customer identified with enough confidence. |
| BR-001-2 | If the customer or period cannot be determined, the bot asks for clarification or escalates. |
| BR-001-3 | Read-only BSS evidence is the source of truth for invoices and customer billing context. |
| BR-001-4 | The pilot must still define minimum identity and access controls before exposing invoice data. |

### User Stories

- US-001 - Identify the customer at the start of the exchange.
- US-002 - Retrieve available invoices and billing periods.
- US-003 - Detect insufficient BSS evidence.

### Open Questions

- OQ-001 - Customer identification by phone and web voice channel.
- OQ-003 - BSS data availability and granularity.

---

## EPIC-002 - Compare Two Invoices Or Billing Periods

**Status:** Ready for delivery split  
**Priority:** High  
**Classification:** V1 core

### Goal

The system identifies price deltas between two invoices or periods and produces a
deterministic business-cause analysis before any LLM wording.

### Scope

- Compare lines that appeared, disappeared or changed.
- Identify usage variation, discounts, prorations, options, taxes, one-off fees
  and adjustments when evidence supports them.
- Calculate the global delta and cause-level deltas using integer cents.
- Expose unreconciled amounts instead of hiding them.

### V1 Delivery Slice

- Compare two explicitly selected periods, or the latest period with the previous
  comparable period.
- Group differences into V1 business categories: expired discount, option or
  service, out-of-bundle usage, proration, one-off fee, adjustment, tax, other.
- Mark the analysis incomplete when confirmed causes do not reconcile the total
  delta sufficiently.

### Out Of Scope

- Predicting the next invoice.
- Commercial negotiation or automatic goodwill gestures.
- Complex multi-customer or multi-contract analysis beyond the provided context.

### Business Rules

| ID | Rule |
|----|------|
| BR-002-1 | The global delta must be explained by traceable causes or declared incomplete. |
| BR-002-2 | Causes are ordered by decreasing impact when amounts are available. |
| BR-002-3 | The LLM never calculates invoice amounts; it words deterministic results. |

### User Stories

- US-004 - Select two invoices or billing periods to compare.
- US-005 - Identify changed invoice lines and amounts.
- US-006 - Identify the main business causes.

---

## EPIC-003 - Explain Invoice Deltas With Evidence

**Status:** Ready for review  
**Priority:** High  
**Classification:** V1 core

### Goal

The customer receives a clear explanation backed by BSS/PDF evidence and enriched
by approved billing or tariff rules when available.

### Scope

- Produce a concise spoken synthesis.
- Cite or summarize the evidence used for each confirmed cause.
- Explain relevant pricing rules from the knowledge base.
- Distinguish confirmed, probable and missing evidence.
- Escalate or stay cautious when proof is insufficient.

### V1 Delivery Slice

- Start every explanation with the total delta and direction of change.
- Present causes by decreasing impact with confirmed amounts.
- Link every confirmed cause to at least one evidence item.
- Use the KB for rule explanation only, never to invent a cause or amount.

### Out Of Scope

- Binding legal answers.
- Commercial resolution guarantees.
- Explaining rules absent from both the KB and BSS evidence.

### Business Rules

| ID | Rule |
|----|------|
| BR-003-1 | Every explanation is tied to evidence or explicitly states what is missing. |
| BR-003-2 | The KB explains rules but never replaces BSS facts. |
| BR-003-3 | The bot refuses to conclude when available proof is insufficient. |

### User Stories

- US-007 - Receive a synthesis of increase or decrease causes.
- US-008 - Obtain evidence for each cause.
- US-009 - Explain the billing rule behind a delta.

### Open Questions

- OQ-002 - Minimum proof threshold for answering without escalation.

---

## EPIC-004 - Deliver The Phone Voice2Voice Journey

**Status:** Ready for review  
**Priority:** High  
**Classification:** V1 core

### Goal

A customer can call the bot, ask a billing question orally and receive a reliable
spoken explanation or escalation path.

### Scope

- Start a phone voice conversation.
- Support Twilio/Pipecat as the V1 implementation path while keeping Genesys
  voice entry as a pilot option when the customer environment requires it.
- Understand a billing explanation request.
- Respond orally with acceptable perceived latency.
- Handle clarification, acknowledgement, barge-in and escalation.

### Business Rules

| ID | Rule |
|----|------|
| BR-004-1 | The phone channel supports end-to-end voice interaction. |
| BR-004-2 | If evidence analysis takes time, the bot acknowledges the request before delivering the final explanation. |
| BR-004-3 | The customer can request a human advisor at any time. |

### User Stories

- US-012 - Call the bot for a spoken invoice explanation.
- US-013 - Receive a quick spoken acknowledgement during long analysis.
- US-014 - Ask orally for transfer to an advisor.

---

## EPIC-005 - Deliver The Web Voice2Voice Journey

**Status:** Ready for review  
**Priority:** High  
**Classification:** V1 core

### Goal

A customer can use a web page to speak with the bot, receive a spoken answer and
see useful visual synthesis when available.

### Scope

- Start a web voice conversation.
- Display synthesis and evidence when available.
- Allow text as a complementary input without replacing Voice2Voice.

### Business Rules

| ID | Rule |
|----|------|
| BR-005-1 | Web voice provides the same business reliability as phone voice. |
| BR-005-2 | Written input complements Voice2Voice; it does not replace the V1 voice requirement. |
| BR-005-3 | Displayed evidence matches the spoken explanation. |

### User Stories

- US-015 - Ask from a web voice chat.
- US-016 - Read the synthesis on the web page.
- US-017 - Use text to complement a voice question.

---

## EPIC-006 - Escalate To A Human Advisor

**Status:** Ready for review  
**Priority:** High  
**Classification:** V1 core

### Goal

The customer is transferred or prepared for transfer when they ask for a human or
when the bot cannot answer safely.

### Scope

- Detect explicit advisor requests.
- Detect insufficient evidence, unusable extraction or unresolved deltas.
- Provide a useful summary for the human advisor through the Genesys handoff
  path.
- Attach the permitted backend handoff context to the Genesys interaction before
  advisor transfer when Genesys is used.
- Keep full Genesys Audio Connector voice routing separate from the mandatory V1
  escalation contract unless the pilot environment requires it.

### Business Rules

| ID | Rule |
|----|------|
| BR-006-1 | Every explicit advisor request triggers the handoff path. |
| BR-006-2 | The bot escalates when it lacks enough proof to explain the delta. |
| BR-006-3 | The handoff context helps the customer avoid repeating the whole request. |
| BR-006-4 | V1 escalation targets Genesys for advisor handoff; full Genesys voice routing is a separate pilot option. |
| BR-006-5 | Genesys remains the contact-center system of record; the backend remains the owner of escalation policy and handoff content. |

### User Stories

- US-018 - Be transferred on explicit request.
- US-019 - Be transferred when the bot lacks enough certainty.
- US-020 - Provide the advisor with usable context.
- US-033 - Hand off to Genesys with advisor context.

---

## EPIC-007 - Provide Web Synthesis And Evidence

**Status:** Ready for review  
**Priority:** Medium  
**Classification:** V1 enabler

### Goal

The customer or advisor can consult a clear view of the invoice delta, main causes
and supporting evidence after or during the spoken explanation.

### Scope

- Display the global delta.
- Display the main causes and their contribution.
- Display line-by-line differences when the web interface is available.
- Display evidence and known limits when available.

### User Stories

- US-021 - Consult the global delta.
- US-022 - Consult cause details.
- US-023 - See evidence and analysis limits.
- US-030 - Consult line-by-line invoice differences.

---

## EPIC-008 - Guarantee Trust, Security And Auditability

**Status:** Ready for review  
**Priority:** High  
**Classification:** V1 enabler

### Goal

The bot handles sensitive billing data safely and leaves enough traceability for
support, audit and dispute handling.

### Scope

- Limit exposed personal and billing data.
- Log sensitive consultation outcomes for audit.
- Make analysis limits visible.
- Keep BSS access read-only.

### User Stories

- US-024 - Protect personal data exposed to the customer.
- US-025 - Audit sensitive consultations.
- US-026 - Disclose analysis limits.

---

## EPIC-009 - Measure Conversational Quality And V1 Performance

**Status:** Ready for review  
**Priority:** High  
**Classification:** V1 pilot gate

### Goal

The team can validate whether the V1 voice journey is acceptable and identify
where conversations fail or escalate.

### Scope

- Measure voice timing points by pipeline slice: channel ingress, end-of-turn,
  STT, backend first token or action, BSS/PDF evidence, comparison, RAG, LLM,
  TTS first audio, channel egress and Genesys handoff.
- Measure invoice comparison response time for conversational use.
- Track escalations and unresolved questions.
- Correlate Genesys, voice runtime, backend, BSS/PDF, LLM, TTS and handoff events
  with a shared correlation id.
- Support OpenTelemetry-style span collection and dashboards for p50, p95 and
  p99 by channel and provider configuration.
- Combine Genesys contact-center metrics with AI-layer metrics for pilot review.
- Support the ADR-0018 pilot criterion before any production SLO claim.

### User Stories

- US-027 - Measure key voice journey timings.
- US-028 - Track escalations and their reasons.
- US-029 - Track unresolved questions.
- US-032 - Measure invoice comparison response time.

---

## EPIC-010 - Validate The BSS/PDF Evidence Fixture Path

**Status:** Draft  
**Priority:** High  
**Classification:** V1 enabler

### Goal

The team can validate the V1 invoice explanation behavior before real BSS sandbox
access is fully stable, using realistic fixtures and extraction statuses.

### Scope

- Define realistic fixture journeys for nominal, expired discount, overage,
  proration, insufficient data and unreliable extraction cases.
- Cover `parseable`, `partial` and `unusable` invoice extraction statuses.
- Keep amounts normalized as integer cents internally.
- Keep fixture evidence readable by Product, Billing, QA and Engineering.
- Validate that the billing/pricing KB contains the rules needed to explain the
  first V1 fixture journeys.

### Out Of Scope

- Building generic Confluence/PDF/database KB connectors.
- Replacing the BSS.
- Treating mock fixtures as production truth.

### Business Rules

| ID | Rule |
|----|------|
| BR-010-1 | A V1 fixture must demonstrate either reliable explanation or a safe limitation/escalation path. |
| BR-010-2 | Fixture amounts use integer cents after unit verification. |
| BR-010-3 | Partial or unusable extraction must never lead to confirmed unsupported amounts. |

### User Stories

- US-010 - Handle invoice extraction status.
- US-011 - Use realistic BSS/PDF fixtures for V1 validation.
- US-031 - Validate billing and pricing KB content for V1.

### Open Questions

- OQ-004 - Invoice PDF extraction reliability and fixture coverage.
