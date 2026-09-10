# TASK-BE-045 — Cadrage: wiring the billing chain behind the answer engine

**Status:** Cadrage (design, pre-implementation) — 2026-09-10. **Decisions D1–D3 locked (2026-09-10, see §3).** ADR-0051 to be written next; implementation not started (awaiting go).
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

## 2. Target flow (locked)

For BE-045 the chain is exposed as a **dedicated backend endpoint** (D3c) —
`POST /api/conversation/billing-explain` — that receives the identity claim + optional
invoice ref + transcript, so `/converse` and the voice runtime stay untouched this ticket.
The deterministic explanation is injected as **grounding evidence** (D1a) into the existing
`AnswerGeneratorPort`; a deterministic **billing-intent detector** (D2a) is built behind a
port and used by the endpoint as an intent guard (and is the reusable capital for the later
`/converse` routing follow-up).

```
POST /billing-explain (channel + reference + optional invoice_id + transcript)
  → [D2a intent guard] billing-explanation? ──no──▶ decline/redirect (not a billing turn)
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

## 3. Decisions (locked 2026-09-10)

### D1 — How the deterministic result reaches the LLM (DEC-002) → **D1a**

Build a deterministic explanation string and inject it as `RetrievedEvidence.text`; reuse
`AnswerGeneratorPort` + `OutputGuardrail` untouched. The LLM only rephrases; amount-grounding
passes by construction. Minimal blast radius.
_(Rejected: D1b return text as-is, no LLM — too robotic; D1c structured grounding contract —
changes the LLM adapter for no pilot benefit.)_

### D2 — Billing-explanation intent detection → **D2a**

Deterministic billing-intent detector (FR/EN, word-boundary keyword sets, env-tunable), same
pattern as `ClosingIntentDetector`, behind a port. In BE-045 it is the endpoint's **intent
guard**; it is the reusable component the later `/converse` routing will call.
_(Rejected for now: D2b channel-only signal; D2c embedding classifier — heavier, BUG-007/OQ-008.)_

### D3 — Identity + invoice plumbing → **D3c**

Backend-only for BE-045: a dedicated `POST /api/conversation/billing-explain` (channel +
reference + optional `invoice_id` + transcript in the body) + tests. `/converse` and the voice
runtime stay untouched; their routing + reference plumbing is an explicit follow-up ticket.
Smallest change, fastest to prove the whole chain end-to-end.
_(Deferred: D3a `ConverseRequest`/envelope fields + `/converse` branch; D3b in-dialog capture.)_

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

## 6. BE-045 sub-tasks (D1–D3 locked)

1. **ADR-0051** — record the billing↔answer integration decision (D1a evidence injection,
   D2a deterministic intent detector, D3c dedicated endpoint, escalation mapping) — write first.
2. `BillingIntentDetector` (domain, FR/EN word-boundary keywords, env-tunable) behind a port
   (D2a); unit-tested. Used by the endpoint as an intent guard.
3. `BillingExplanationUseCase` (billing context) orchestrating identity → comparable invoices
   → compare → readiness → deterministic explanation → `BillingExplanationOutcome`
   (answer/evidence + confidence + escalation reason), fail-closed on every degraded branch (§4).
4. Deterministic `BillingExplanationComposer` (amounts + causes + residual → grounded text,
   language-aware via `AnswerLanguage`), unit-tested on the six journeys; feeds D1a evidence.
5. `POST /api/conversation/billing-explain` controller + DTOs (D3c), api-key gated like
   `/answer`; reuses `AnswerGeneratorPort` + `OutputGuardrail` (D1a). No `/converse` change.
6. Escalation reason extension (`IDENTITY_UNVERIFIED`, `BILLING_UNEXPLAINED`) + by-reference
   handoff content, threaded through `PrepareEscalationHandoffUseCase` (ADR-0019).
7. OTel spans/metrics/logs (§5) + correlation-id continuity; no PII / no full invoice.
8. Tests: end-to-end journeys (grounded phrasing, PARTIAL caveat, INSUFFICIENT escalation,
   identity unresolved/ambiguous, <2 invoices), OutputGuardrail amount-grounding, ArchUnit.
9. Docs: architecture.md + API docs (new endpoint) + ADR-0051; adversarial review before QA.

**Follow-up ticket (out of BE-045):** route billing from `/converse` (D3a request/envelope
fields + `/converse` intent branch) + voice-runtime plumbing, reusing the BE-045 use case +
detector.

---

## 7. Out of scope for BE-045

- Real Galaxion adapter (BE-047), real PDF parsing (BE-041 follow-up), like-for-like invoice
  matching, KB entries for causes (BE-046), strong auth (OQ-001), final confidence thresholds
  (OQ-002), QA/latency validation (QA-019/020).
