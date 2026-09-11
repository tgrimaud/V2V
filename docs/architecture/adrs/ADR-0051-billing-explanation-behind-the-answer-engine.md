# ADR-0051: Billing Explanation Behind The Answer Engine

## Status

Accepted (2026-09-11)

> Records how the deterministic billing chain (identity → comparable invoices → comparison
> → confidence gate) is connected to the conversation answer engine so the LLM **only
> phrases** an already-computed, grounded result (**DEC-002**), and how the bot escalates
> **fail-closed**. Complements **ADR-0003** (deterministic billing, LLM never computes),
> **ADR-0050** (fail-closed identity), **ADR-0019** (by-reference escalation handoff), and
> **DEC-002** (LLM phrases only). Implementation: **TASK-BE-045** (Sprint 14). Full options
> and flow: `docs/architecture/billing-answer-integration-cadrage.md`.

## Context

Through TASK-BE-038…044 the billing context can, on fixtures, resolve a customer identity,
list comparable invoices, compare two invoices deterministically, and judge whether the
result is explainable. None of it is connected to the answer engine yet.

The answer engine (`com.voicesupport.conversation`, verified in code) has hard constraints
that shape the integration:

- **No runtime intent classifier** (BUG-007): `/converse` passes `domain=null`; there is no
  billing-vs-support router and `DomainClassifierPort` is ingestion-only.
- **No customer/account identity field** on `ConverseRequest` / `ChannelEnvelope`.
- The **only** grounding channel to the LLM is `List<RetrievedEvidence>(text, …)` joined into
  the `{context}` system-prompt slot; the LLM user message is the question only.
- **`OutputGuardrail` enforces DEC-002**: every currency amount in the answer must appear in
  the concatenated evidence text, else `UNGROUNDED` → fallback.
- Escalation is verdict-mapped (`EscalationReason.fromVerdict`, today `LOW_CONFIDENCE` /
  `UNGROUNDED`), then materialized by-reference (`PrepareEscalationHandoffUseCase`, ADR-0019).

We need to expose the billing explanation without letting the LLM compute anything, without
weakening the amount guardrail, and without prematurely reworking `/converse`, its REST
contract, or the voice runtime.

## Decision

1. **Ground, do not compute (D1a).** The billing chain builds a **deterministic explanation
   text** (causes + amounts + residual, language-aware) and injects it as a synthetic
   `RetrievedEvidence`. The existing `AnswerGeneratorPort` phrases it and the existing
   `OutputGuardrail` vets it **unchanged**. Because every amount is already in the injected
   evidence, DEC-002 amount-grounding holds **by construction** and the LLM can only restate,
   never invent, figures. No new "facts vs phrasing" LLM contract.

2. **Deterministic intent detection (D2a).** A `BillingIntentDetector` domain service (FR/EN,
   word-boundary keyword sets, env-tunable, behind a port — same shape as
   `ClosingIntentDetector`) decides whether a turn is a billing-explanation request. No
   embedding/query classifier (BUG-007/OQ-008). In BE-045 it is the **intent guard** of the
   billing endpoint; it is the reusable component the later `/converse` routing will call.

3. **Dedicated endpoint first (D3c).** BE-045 exposes the chain as
   `POST /api/conversation/billing-explain` (body: channel + reference + optional `invoice_id`
   + transcript/question, api-key gated like `/answer`). `/converse`, its DTO/envelope and the
   voice runtime stay **untouched** this ticket; routing billing from `/converse` (request/
   envelope fields + intent branch) + runtime plumbing is an explicit **follow-up ticket** that
   reuses the same use case + detector.

4. **Fail-closed everywhere (BR-002-1, BR-003).** The orchestration
   (`BillingExplanationUseCase`) never phrases amounts unless it has a `RESOLVED` identity and
   an `EXPLAINABLE`/`PARTIAL` comparison:
   - identity `UNRESOLVED`/`AMBIGUOUS` → ask for a valid reference, then escalate;
   - `< 2` comparable invoices or readiness `INSUFFICIENT` → escalate, **no amounts**;
   - readiness `PARTIAL` → phrase with a caveat (residual surfaced);
   - any BSS/extraction failure → safe fallback + escalate.
   New escalation reasons `IDENTITY_UNVERIFIED` and `BILLING_UNEXPLAINED` are threaded through
   the existing by-reference handoff (ADR-0019).

5. **Structured source first, PDF fallback.** The explanation is built from the structured
   `BssBillingPort`; the `InvoicePdfExtractorPort` (ADR-0005) is the fallback only when the
   structured source is unavailable. Both are fixtures for the pilot.

6. **Observability is mandatory (runtime-affecting).** A billing trace slice under the turn
   correlation id: spans/metrics/structured logs for `billing.identity.resolve`,
   `billing.invoices.list`, `billing.invoice.compare`, `billing.readiness.assess`, plus outcome
   events (`resolved/unresolved/ambiguous`, `explainable/partial/insufficient`, `escalated`).
   **No PII** (never the raw reference — ADR-0050) and **no full invoice content** in logs.

## Consequences

- The whole billing chain is provable end-to-end on fixtures without touching `/converse`, the
  REST contract or the voice runtime — smallest blast radius, fastest QA.
- DEC-002 is preserved with **no** change to the LLM adapter or `OutputGuardrail`; the amount
  guardrail keeps protecting the injected evidence.
- Escalation stays uniform (verdict-mapped + by-reference handoff), extended with billing reasons.
- The intent detector is reusable capital for the later `/converse` routing.
- **Trade-off:** a second answer entry point (`/billing-explain`) exists until the follow-up
  folds billing into `/converse`; acceptable and explicitly temporary.
- **Residual:** deterministic keyword intent detection will mis-route some phrasings; on the
  dedicated endpoint the impact is bounded (the caller already targets billing), and the
  detector thresholds/keywords are env-tunable and revisited when `/converse` routing lands.

## Alternatives Considered

- **Let the LLM read invoices / compute the diff** — rejected (DEC-002, ADR-0003): the LLM must
  never compute amounts.
- **Return the deterministic text as-is, no LLM** — rejected for the pilot: robotic, loses the
  conversational voice; kept as a possible degraded mode only.
- **New structured grounding contract into the prompt builder** — rejected: changes the LLM
  adapter for no pilot benefit over evidence injection.
- **Embedding/query intent classifier** — rejected now: heavier and BUG-007/OQ-008 caution
  against forcing a per-query domain.
- **Route billing through `/converse` immediately** (request/envelope fields or in-dialog
  identity capture) — deferred to a follow-up: REST contract + runtime changes and multi-turn
  identity state are avoidable while proving the chain.
