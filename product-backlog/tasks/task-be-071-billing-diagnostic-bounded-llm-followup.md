# TASK-BE-071 — Billing clarify increment C: deterministic trigger + bounded LLM follow-up

**Type:** Technical task (backend — conversation flow + guardrails + LLM prompt)
**Status:** 🔵 Implemented, pending QA + user validation (2026-10-08). Increment **C** (target) of US-043; builds on TASK-BE-070.
**Adversarial review 93/100 (Pass, 2026-10-08)** — no blocking finding; residual (accepted): memory-derived streak resets on an interleaved non-opener turn (by design); pilot clarify improves retrieval/escalation context only, not amount accuracy (no live BSS); per-sub-type clarify deferred (OQ-043-b). Review: [`docs/qa/task-be-071-adversarial-review.md`](../../docs/qa/task-be-071-adversarial-review.md). ADR: [ADR-0056](../../docs/architecture/adrs/ADR-0056-bounded-billing-clarify-dialogue.md).
**Sprint:** Sprint 16 (`feat/sprint-16-billing-clarify`). Ticket branch `task/TASK-BE-071-billing-diagnostic` forked **off the TASK-BE-070 branch** (C depends on D's un-merged code); git reconciles at the sprint merge.

## Implementation (2026-10-08)

Delivered as a `BillingDiagnosticConversationService` **decorator** implementing both
`ConverseUseCase` + `ConverseStreamUseCase`, wrapping the real `ConversationService` /
`StreamingConversationService` delegates (the only bean per converse port, wired in
`ConversationConfig`). Deviations from the pre-implementation plan, all improving on it:
- **Clarify count is a streak derived from `ConversationMemoryPort`** (trailing turns whose stored
  customer text is still a billing opener) — no new counter state / no memory-contract change.
- **No retrieval deflection by construction:** the clarify is produced *before* delegating, so the
  confidence/grounding gate never runs on a clarify turn (stronger than "mirror the opener clarify").
- **Cap → escalation:** at the cap the turn returns `AnswerLanguage.handoffSentence()` (LOW_CONFIDENCE
  ⇒ `EscalationReason`), carrying the collected context (ADR-0019).
- LLM wording via a new out-port `ClarifyingQuestionGeneratorPort` on `AbstractChatClientAnswerAdapter`
  (`CLARIFY_SYSTEM_PROMPT`, no RAG context, `AnswerLanguage.clarifyDirective()` appended recency-last),
  **DEC-002-vetted** by the existing `OutputGuardrail`.
- Configurable `voice-support.conversation.billing-clarify.max-questions` (env
  `CONVERSATION_BILLING_CLARIFY_MAX_QUESTIONS`, default **2**; `<= 0` disables ⇒ TASK-BE-070 behaviour).
- Telemetry `voice_support.billing_clarify` (`asked`/`cap_escalated`, tags language+channel); clarify
  LLM call timed on `llm_wording`.

Tests: `BillingDiagnosticConversationServiceTest` (12), `ClarifyingQuestionAdapterTest` (4),
`AnswerLanguageTest` (+2), updated `ConversationMemoryConfigWiringTest`. Full backend suite **751 green**
(incl. ArchUnit). Pure domain Spring-free; manual fakes, GIVEN/WHEN/THEN, no Mockito.
**Priority:** Medium
**Epic:** EPIC-005 (Answer engine / knowledge base)
**Delivers:** US-043 (target behavior). **Depends on TASK-BE-070** (increment D) being merged first.
**Related:** TASK-BE-070, BUG-025, DEC-002, TASK-BE-018 (concision), TASK-BE-015 (per-turn language),
ADR-0019 (escalation + collected context), ADR-0009 (channel envelope / conversation memory),
ADR-0013 (`converse-stream` guarded sentences).
**Surfaced by:** user feedback (2026-10-08) + US-043 delivery plan (D then C, user-chosen).

## Context

Increment D (TASK-BE-070) makes the deterministic clarify voice-friendly and a bit broader, but it is
still a single scripted question. The target is a **short, natural diagnostic**: when a billing problem
is under-specified, the assistant asks **one natural follow-up at a time**, up to a bounded maximum,
then answers from the knowledge base or escalates with the collected context.

Chosen approach (hybrid, user-selected "C"): keep the **trigger and the bound deterministic**, let the
**follow-up wording come from the LLM** so it sounds natural and reacts to what the customer already
said — but strictly capped so it cannot loop or drift.

## Scope & decision

**1. Deterministic trigger + bound (orchestration):**
- Decide "billing problem AND under-specified" deterministically (reuse/extend the TASK-BE-070
  `ProblemOpenerDetector` billing path). A specific, answerable question skips the diagnostic (BR5).
- Track a **clarify counter** per conversation in the existing conversation memory
  (`ConversationMemoryPort`, keyed on the ADR-0009 session), reset appropriately. Enforce a configurable
  **max follow-ups** (`voice-support.conversation.billing-clarify.max-questions`, default per OQ-043-a,
  pending Product = 2). After the cap: force the normal grounded answer path, or the ADR-0019 escalation
  with the collected context — never another question (BR3).

**2. Bounded LLM follow-up (prompt):**
- When the trigger fires and the counter is under the cap, run a **follow-up turn** whose job is to ask
  **one** short clarifying question, not to answer. Implement via a per-turn directive appended in
  `AbstractChatClientAnswerAdapter.buildSystemMessage(...)` (a new `AnswerLanguage`-owned directive, FR/EN,
  recency-last like the language directive), **suspending the TASK-BE-018 concision "answer" framing** for
  that turn (ask-one-question framing instead).
- The follow-up must obey DEC-002 (ask only; never state an amount) — the `OutputGuardrail` already only
  blocks ungrounded amounts, and a question has none, so a clarify turn passes; add a test to lock it.
- Route the clarify turn **without retrieval grounding deflection**: a clarify is not a low-confidence
  answer, so it must not be turned into an advisor hand-off by `RetrievalConfidenceGuardrail`
  (mirror how the BUG-025 opener clarify short-circuits before retrieval).

**3. Collected context → better answer + escalation:**
- Feed the accumulated clarifying exchange (already in conversation history, injected into the system
  message) so the eventual grounded answer and the ADR-0019 escalation hand-off carry the understood
  problem (improves retrieval relevance and advisor context — the real pilot win, since no live BSS).

**Observability (mandatory):**
- Metrics: clarify asked (channel, language), clarify count per conversation, outcome
  (answered-after-clarify vs escalated-after-clarify), and the cap-hit event. Correlation-id carried as
  usual. These satisfy US-043 analytics and let QA verify the bound.

## Acceptance criteria

- An under-specified billing problem produces a **natural, single** follow-up question (LLM-worded,
  FR/EN), not an enumeration; subsequent under-specified turns produce at most the configured maximum of
  follow-ups, then the assistant answers or escalates (bounded, deterministic) — covered by service tests
  with a fake LLM.
- The clarify counter lives in conversation memory, is enforced server-side, and the cap cannot be
  exceeded even if the LLM "wants" to keep asking (orchestration gate, not prompt trust).
- A specific/answerable billing question and an explicit advisor request are not intercepted (BR5).
- DEC-002 preserved on clarify turns (no amount) — locked by a test; `OutputGuardrail` + incremental
  `converse-stream` contract tests stay green.
- A clarify turn is not deflected to a hand-off by the confidence/grounding gate (no-retrieval path),
  mirroring the opener clarify.
- Backend `mvn test` green incl. ArchUnit; pure domain stays Spring-free; beans wired in
  `DomainServiceConfig`. Manual fakes, GIVEN/WHEN/THEN, no Mockito.
- Clarify/outcome telemetry present and asserted.

## Risks / open questions

- OQ-043-a (max follow-ups) — Product decision; default 2 pending.
- OQ-043-c — does the multi-turn diagnostic change the conversation contract enough to need an **ADR**
  (diagnostic state in memory, clarify-turn semantics on `converse`/`converse-stream`)? Architecture to
  decide; if yes, write it before implementation.
- Residual LLM variance on the follow-up wording is accepted because the **trigger and bound are
  deterministic**; the LLM only phrases the single allowed question.
- Latency: a clarify turn is a short LLM turn with no (or minimal) retrieval; confirm it does not regress
  the voice SLO, and measure it as its own slice.
