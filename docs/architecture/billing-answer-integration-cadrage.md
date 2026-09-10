# TASK-BE-045 — Cadrage: wiring the billing chain behind the answer engine

**Status:** Cadrage (design, pre-implementation) — 2026-09-10. Decisions D1–D3 pending user/product/architecture confirmation; will crystallize into **ADR-0051** before coding.
**Scope ticket:** TASK-BE-045 (Sprint 14). Depends on BE-038/039/040/041/042/043/044 (all merged).

> Goal: connect the deterministic billing chain (identity → comparable invoices →
> comparison → confidence gate) to the existing conversation answer engine so that, on a
> billing question, the LLM **only phrases** a grounded, already-computed result (DEC-002),
> and the bot **escalates fail-closed** when identity is unresolved or the result is not
> explainable.

---

## 1. What already exists (verified in code)

Answer engine (`com.voicesupport.conversation`), from the flow map:

- `POST /converse` → `ConversationService` (memory + `answerQuestionUseCase.answer(transcript, **domain=null**, …)`) → `AnswerService` → `RetrievalGroundingService.ground(…)` → `AnswerGeneratorPort.generate(question, evidence, history, language)` → `OutputGuardrail.check(text, evidence, language)`.
- `POST /converse-stream` → `StreamingConversationService` → same grounding, then `GuardedSentenceEmitter` vets **each sentence** before emitting (SSE `chunk`/`done`/`error`).
- **No runtime intent/billing router** (BUG-007). `DomainClassifierPort` is ingestion-only.
- **No customer/account field** on `ConverseRequest` (has `transcript`, `conversationId`, `correlationId`, `channel`, `language`, + envelope `externalSessionId`, `messageId`, `idempotencyKey`, `replyMode`, `escalationContext`).
- Grounding to the LLM is **only** `List<RetrievedEvidence>(text, sourceId, domain, score)` → joined into the `{context}` system-prompt slot.
- `OutputGuardrail` (DEC-002): every currency amount in the answer **must** appear in the concatenated evidence text, else `UNGROUNDED` → fallback.
- Escalation: no `EscalationDetector`; `EscalationReason.fromVerdict` maps only `LOW_CONFIDENCE`/`UNGROUNDED`; `PrepareEscalationHandoffUseCase` builds the by-reference handoff at the controller.

Billing chain (`com.voicesupport.billing`, all merged): `ResolveCustomerIdentityUseCase`, `RetrieveComparableInvoicesUseCase`, `CompareInvoicesUseCase`, `AssessComparisonReadinessUseCase`, `InvoicePdfExtractorPort` (fallback), all on `customer-eir-*` fixtures.

---

## 2. Target flow (proposed)

A new **billing orchestration** use case in the billing context, called by the conversation
layer **before** KB grounding when the turn is a billing-explanation intent:

```
turn (transcript + identity claim + optional invoice ref)
  → [D2 intent] billing-explanation? ──no──▶ existing KB grounding (unchanged)
        │ yes
        ▼
  ResolveCustomerIdentity(claim)
        │ RESOLVED ────────────────┐  UNRESOLVED/AMBIGUOUS ─▶ clarify (ask reference) or escalate (fail-closed)
        ▼                          │
  RetrieveComparableInvoices(account)
        │ ≥2 comparable ───────────┤  <2 ─▶ INSUFFICIENT ─▶ escalate/clarify
        ▼                          │
  CompareInvoices(prev, current)   │
        ▼                          │
  AssessComparisonReadiness(cmp)   │
        │ EXPLAINABLE / PARTIAL     │  INSUFFICIENT ─▶ escalate (no amounts phrased)
        ▼
  Build deterministic explanation TEXT (FR/EN) from causes + amounts + residual
        ▼
  Hand that text as grounding evidence ──▶ existing AnswerGeneratorPort (LLM phrases only)
        ▼
  existing OutputGuardrail vets amounts ──▶ answer / stream (unchanged contract)
```

Key design choice (**D1**): the deterministic explanation is injected as a synthetic
`RetrievedEvidence` (with every amount in its text) so the **existing** `AnswerGeneratorPort`
+ `OutputGuardrail` are reused unchanged and DEC-002 holds automatically (LLM can only
restate amounts that are already in the grounded evidence). No new "facts vs phrasing"
contract, no LLM math.

---

## 3. Decisions to confirm before coding

### D1 — How the deterministic result reaches the LLM (DEC-002)

- **D1a (recommended):** Build a deterministic explanation string and inject it as
  `RetrievedEvidence.text`; reuse `AnswerGeneratorPort` + `OutputGuardrail` untouched. The
  LLM only rephrases; amount-grounding passes by construction. Minimal blast radius.
- D1b: Return the deterministic text **as the answer** and skip the LLM (LLM adds nothing;
  most deterministic, least natural). 
- D1c: New structured grounding contract (facts object) into the prompt builder. Most work,
  changes the LLM adapter contract.

### D2 — How a billing-explanation intent is detected (no runtime classifier today)

- **D2a (recommended for pilot):** Deterministic billing-intent detector (FR/EN,
  word-boundary keyword sets, env-tunable), same pattern as `ClosingIntentDetector`. Cheap,
  deterministic, testable. Behind a port so it's swappable.
- D2b: Explicit channel signal — the caller sets a billing mode / the presence of an
  `invoice_id`/`customer_reference` triggers the billing branch. Simplest, but needs the
  channel to know.
- D2c: Embedding/similarity classifier at query time — heavier; BUG-007/OQ-008 caution
  against forcing a query domain.
- Likely **D2a + D2b combined**: billing branch fires when intent detector matches **and/or**
  a customer/invoice reference is present.

### D3 — How identity + invoice selection are plumbed for the pilot

- **D3a (recommended):** Add optional `customer_reference` (+ optional `invoice_id`) to
  `ConverseRequest` + `ChannelEnvelope`, supplied by the channel/test harness; if billing
  intent fires without a usable reference → clarify (ask for it) then escalate. REST contract
  change (documented), voice-runtime plumbing tracked as a sub-item.
- D3b: In-dialog identity capture (multi-turn: bot asks the reference, stores it in memory,
  resumes). No contract change but needs conversational state — bigger.
- D3c: Backend-only for BE-045: expose a dedicated `POST /api/conversation/billing-explain`
  (identity + invoice in body) + tests, defer the `/converse` routing + runtime plumbing to a
  follow-up. Smallest, keeps `/converse` untouched, fastest to prove the chain end-to-end.

Invoice pair: compare the **two most recent comparable** invoices (BE-039 order); like-for-like
`InvoiceLevel`/subscription matching stays deferred (already noted on BE-039). `<2` →
INSUFFICIENT.

Source: **structured BSS first** (`BssBillingPort`), PDF extractor (BE-041) as fallback only if
BSS is unavailable — both fixtures for the pilot; runtime structured-vs-PDF choice can be a thin
wrapper or deferred.

---

## 4. Escalation & degraded outcomes (fail-closed)

| Situation | Outcome | Mechanism |
|---|---|---|
| Identity UNRESOLVED/AMBIGUOUS | Ask for a valid reference, then escalate | clarify text / `GeneratedAnswer.fallback` + escalation reason |
| < 2 comparable invoices | Cannot compare → escalate/clarify | readiness INSUFFICIENT-equivalent |
| Readiness INSUFFICIENT | Escalate, **no amounts phrased** | fallback + escalation, by-reference handoff |
| Readiness PARTIAL | Phrase with a caveat (residual mentioned) | evidence text includes residual |
| BSS/extraction failure | Safe fallback + escalate | try/catch → fallback |

Requires extending escalation mapping (today only `LOW_CONFIDENCE`/`UNGROUNDED`) with billing
reasons (e.g. `IDENTITY_UNVERIFIED`, `BILLING_UNEXPLAINED`), threaded into the existing
`PrepareEscalationHandoffUseCase` (by-reference, ADR-0019).

---

## 5. Observability (mandatory — runtime-affecting)

New billing trace slice under the turn correlation id, spans + `voice_support.slice`-style
metrics + structured logs (p50/p95/p99 capable):

- `billing.identity.resolve` (attrs: channel, status; **never** the raw reference — ADR-0050),
- `billing.invoices.list`, `billing.invoice.compare`, `billing.readiness.assess`
  (attrs: confidence, escalate, `unexplained` magnitude — not full invoice),
- outcome events: `resolved/unresolved/ambiguous`, `explainable/partial/insufficient`,
  `escalated`.
- No PII / no full invoice content in logs.

---

## 6. Proposed BE-045 sub-tasks (once D1–D3 fixed)

1. `BillingExplanationUseCase` (billing context) orchestrating identity → list → compare →
   readiness → deterministic explanation builder (FR/EN) → `ExplanationOutcome` (text +
   evidence + escalate reason).
2. Deterministic `BillingExplanationComposer` (amounts + causes + residual → grounded text,
   language-aware), unit-tested on the six journeys.
3. Conversation wiring per **D2/D3** (intent branch or dedicated endpoint), reusing
   `AnswerGeneratorPort` + `OutputGuardrail` per **D1**.
4. Escalation reason extension + handoff content for billing.
5. OTel spans/metrics/logs (§5) + correlation-id continuity.
6. Tests: billing journeys end-to-end (grounded phrasing, PARTIAL caveat, INSUFFICIENT
   escalation, identity unresolved/ambiguous), OutputGuardrail amount-grounding, ArchUnit.
7. Docs: architecture + API (if REST contract changes) + ADR-0051.

---

## 7. Out of scope for BE-045

- Real Galaxion adapter (BE-047), real PDF parsing (BE-041 follow-up), like-for-like invoice
  matching, KB entries for causes (BE-046), strong auth (OQ-001), final confidence thresholds
  (OQ-002), QA/latency validation (QA-019/020).
