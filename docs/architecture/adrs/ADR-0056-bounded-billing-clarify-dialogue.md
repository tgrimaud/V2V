# ADR-0056: Bounded, memory-derived billing clarify dialogue on `/converse`

## Status

Accepted (2026-10-08)

## Context

US-043 asks the assistant to **ask a clarifying question before answering** a vague billing
problem, instead of grounding a weak RAG match (BUG-005 family) or escalating too early. It is
delivered in two increments:

- **Increment D (TASK-BE-070, shipped):** a *deterministic, single* canned clarify. The
  `ProblemOpenerDetector` recognises an under-specified billing opener (BILLING topic, no concrete
  anchor such as a figure/"euros", not an escalation request) and the `InputGuardrail` returns one
  fixed clarify sentence (`problem_opener_billing`). It never remembers that it already asked, so a
  customer who re-states the problem gets the *same* canned sentence again — no progression, no
  bound, no natural wording.

- **Increment C (TASK-BE-071, this ADR):** turn the single canned clarify into a **short, bounded,
  natural clarifying dialogue** — the LLM phrases the follow-up question, the dialogue is capped,
  and at the cap the turn hands off to an advisor with the collected context.

Three design forces shaped the increment:

1. **DEC-002 must hold.** The clarify is produced by the LLM, so a stray amount/date must never be
   voiced. The pilot has **no live BSS/invoice data** on `/converse`, so a clarify can only improve
   *retrieval relevance* and *escalation context* — never state an amount.
2. **Minimal blast radius.** The stateful entry points (`ConverseUseCase` /
   `ConverseStreamUseCase`, backed by `ConversationService` / `StreamingConversationService`) and
   the `ConversationMemoryPort` are heavily used and tested. The increment must not fork the
   pipeline, add a memory column, or change any out-port/adapter contract.
3. **Deterministic trigger & bound.** Whether to clarify and how many times must **not** depend on
   LLM/prompt trust — only the *wording* may. This keeps the behaviour auditable and testable, in
   line with the "no runtime query classifier" stance (BUG-007 / OQ-008).

## Decision

### D1 — A decorator over the stateful converse pipelines

A single application service `BillingDiagnosticConversationService` implements **both**
`ConverseUseCase` and `ConverseStreamUseCase` and **wraps** the real `ConversationService` /
`StreamingConversationService` as plain delegate objects (constructed in `ConversationConfig`, not
exposed as their own beans). It is the only bean assignable to each converse port, so every
existing consumer (controllers, routing) is injected the decorator with no call-site change.

Per turn it computes one of three actions:

- **PROCEED** → delegate to the normal pipeline unchanged (RAG grounding → LLM → OutputGuardrail).
- **ASK_CLARIFY** → return/emit ONE LLM-worded clarifying question.
- **ESCALATE_AT_CAP** → return/emit the advisor hand-off sentence.

A turn is a **clarify turn iff** `max-questions > 0` **and** the transcript is an under-specified
billing opener per the TASK-BE-070 `ProblemOpenerDetector` (`Topic.BILLING`). Any other turn — a
concrete/answerable question, the customer's clarifying *answer*, an advisor request, off-topic —
is PROCEED. This reuses the increment-D detector as the single trigger source of truth; there is no
new intent classifier.

### D2 — The bound is a streak **derived from conversation memory** (no new state)

The clarify count is not a persisted counter. It is derived on the fly as the number of **trailing
turns in `ConversationMemoryPort.recentTurns(id)` whose stored customer text is still an
under-specified billing opener** (`billingStreak`). Because each clarify turn is appended to memory
like any other turn, *the turns ARE the counter*:

- 1st billing opener → streak 0 → ASK_CLARIFY (streak becomes 1 after append).
- 2nd consecutive billing opener → streak 1 → ASK_CLARIFY (→ 2).
- At `streak == max-questions` → ESCALATE_AT_CAP.
- The customer's **real answer** (a non-opener turn) breaks the streak → the next billing opener
  starts a fresh episode.

This needs **zero** change to `ConversationMemoryPort`, its in-memory/Redis adapters, or the
`ConversationTurn` value object. It also means the bound is naturally per-conversation and resets
correctly across episodes.

### D3 — The LLM phrases the question; the backend vets it (DEC-002)

A new conversation out-port `ClarifyingQuestionGeneratorPort`
(`generateClarifyingQuestion(question, history, language)`) is implemented by the **same** provider
LLM adapter (`AbstractChatClientAnswerAdapter`, so Mistral/Ollama/OpenAI all get it for free). It
sends a dedicated **ask-one-question** system prompt (`CLARIFY_SYSTEM_PROMPT`): no RAG context, must
ask exactly one short question, must not answer, must not state any amount/date, and must build on
the conversation history so it does not repeat an earlier question. The per-language
`AnswerLanguage.clarifyDirective()` is appended **last** (recency), mirroring the TASK-BE-015
answer-language ordering.

The generated question is then **DEC-002-vetted** by the existing `OutputGuardrail.check(question,
emptyEvidence, language)`: with empty evidence any voiced amount is UNGROUNDED and any blank/handoff
is LOW_CONFIDENCE → the clarify is **dropped** and replaced by the hand-off. A well-formed question
voices no figure, so it passes. No new guardrail logic is introduced.

### D4 — At the cap, escalate with the collected context (never another question)

When the streak reaches `max-questions`, the turn returns `AnswerLanguage.handoffSentence()` as a
`LOW_CONFIDENCE` fallback (which carries the exact `handoffMarkers()` the OutputGuardrail / voice
runtime recognise and maps to an escalation reason via `EscalationReason.fromVerdict`). The two or
three billing turns already live in conversation memory, so the advisor hand-off carries the
collected context (ADR-0019 by-reference handoff). The clarify fallback itself is a `CLARIFY`
verdict → **no** escalation, so a mid-dialogue clarify never produces a spurious hand-off.

### D5 — Configurable bound (OQ-043-a)

`voice-support.conversation.billing-clarify.max-questions` (env
`CONVERSATION_BILLING_CLARIFY_MAX_QUESTIONS`, **default 2**) sets the cap.
`max-questions <= 0` **disables** the diagnostic entirely: every turn PROCEEDs and the TASK-BE-070
single canned clarify remains the behaviour. This gives a safe, per-deployment kill switch and lets
the pilot tune the number of questions without a rebuild.

### D6 — Observability

A dedicated meter + structured log `voice_support.billing_clarify`
(`BackendTelemetry.recordBillingClarify(event, language, count)`) emits `event=asked` (with the
current streak count) on each clarify and `event=cap_escalated` at the cap, tagged by language and
channel. The clarify LLM call is timed on the existing `llm_wording` slice (same bounded-call +
timeout budget as answers), so a slow provider degrades to the sanitized path.

## Consequences

**Positive**

- A vague billing opener now triggers a *natural*, *bounded* clarify dialogue that progresses and
  then escalates with context, instead of repeating one canned sentence forever.
- Trigger and bound stay **deterministic and auditable**; only the wording is LLM-generated, and it
  is DEC-002-vetted before it is voiced.
- Zero change to memory/out-port/adapter contracts and no pipeline fork — the decorator is the only
  bean assignable to the converse ports, and `mvn test` runs with no `@SpringBootTest`.
- One kill switch (`max-questions <= 0`) reverts to the increment-D behaviour.

**Negative / residual**

- The streak is derived from the *trailing* billing-opener turns, so an interleaved non-opener turn
  intentionally resets the episode. This is the desired semantics (a real answer ends clarifying)
  but means a customer who oscillates opener → chit-chat → opener re-starts the budget. Acceptable
  for the pilot; revisit only if abuse appears.
- On the pilot `/converse` has no live invoice data, so the clarify improves retrieval/escalation
  context only, not amount accuracy. When live BSS lands (OQ-002), the collected context should feed
  the deterministic billing chain (ADR-0052/0055) rather than only RAG — tracked as a follow-up.
- The per-sub-type clarify specialisation (billing *increase* vs *new charge* vs *promo expiry*,
  OQ-043-b) is **not** modelled; a single billing clarify prompt is used.

## Alternatives considered

- **Thread a "suppress answer + ask" flag through all three layers.** Rejected: couples the
  controllers, both conversation services and the LLM step; large blast radius for a bounded
  feature. The decorator keeps the policy in one testable service.
- **Persist an explicit clarify counter (new memory column / Redis key).** Rejected: changes the
  `ConversationMemoryPort` contract and both adapters for state that the stored turns already
  encode. The memory-derived streak is contract-free and resets correctly across episodes.
- **Let the LLM decide when to stop asking.** Rejected: violates the deterministic-trigger/bound
  force (D1/D2) and DEC-002 auditability; the LLM only phrases, it never decides to clarify or when
  to stop.
- **Keep the increment-D single canned clarify.** Rejected by US-043: it never progresses and reads
  robotic on the second turn.

## References

- US-043 (ask a clarifying question before answering a billing problem)
- TASK-BE-070 (increment D — deterministic single clarify, `ProblemOpenerDetector`)
- TASK-BE-071 (increment C — this ADR, bounded LLM-worded clarify dialogue)
- ADR-0034 (vague-turn clarify band), ADR-0019 (by-reference escalation handoff)
- DEC-002 (LLM only phrases grounded content; never invents amounts)
- ADR-0052 / ADR-0055 (deterministic billing chain + `/converse` routing — the live-data follow-up)
- BUG-007 / OQ-008 (no runtime query classifier), BUG-005 (weak-match grounding)
- OQ-043-a (configurable question count — resolved: default 2), OQ-043-b (per-sub-type clarify — open)
