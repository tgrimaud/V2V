# Adversarial Code Review — TASK-BE-071 (US-043 increment C: bounded billing clarify dialogue)

Reviewed change: `BillingDiagnosticConversationService` decorator + `ClarifyingQuestionGeneratorPort`
(LLM adapter method `generateClarifyingQuestion` + `CLARIFY_SYSTEM_PROMPT`), `AnswerLanguage`
`clarifyDirective()` / `handoffSentence()`, `BackendTelemetry.recordBillingClarify`,
`ConversationConfig` rewiring, `application.yml` `billing-clarify.max-questions`, ADR-0056.

## Verdict

Proceed.

## Satisfaction Score

Score: 93/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | Streak derived from memory resets if the customer interleaves a non-opener turn between two openers, so an oscillating customer can re-arm the budget. | `billingStreak()` counts only *trailing* opener turns. | Accepted by design (a real answer must end the episode); revisit only if abuse is observed. Documented in ADR-0056 residual. |
| Low | On the pilot the clarify improves retrieval/escalation context only, not amount accuracy (no live BSS on `/converse`). | US-043 scope note; DEC-002 unchanged. | Follow-up: feed the collected context into the ADR-0052/0055 billing chain when live BSS lands (OQ-002). |
| Low | A single billing clarify prompt is used; billing sub-types (increase / unknown charge / promo expiry) are not specialised. | `CLARIFY_SYSTEM_PROMPT` is generic. | OQ-043-b (Product) — out of this increment. |
| Info | The clarify LLM call adds one extra provider round-trip on an under-specified billing opener turn. | `generateClarifyingQuestion` timed on `llm_wording`. | It replaces (does not add to) the normal answer LLM call on that turn, and is bounded by the same timeout; net latency is comparable. QA to confirm on the pilot. |

## Story Coverage

| Acceptance criterion (US-043) | Covered? | Evidence |
|---|---|---|
| Under-specified billing problem → one short question, no enumeration (BR1/BR2/BR4) | Yes | `first_billing_opener_asks_llm_clarify`; `CLARIFY_SYSTEM_PROMPT` asks exactly one question, no answer; DEC-002 vetting. |
| Clarifying dialogue is bounded; then answer-or-advisor, no further question (BR3) | Yes | `bounds_clarifies_then_escalates`, `bound_is_configurable`; `decide()` → ESCALATE_AT_CAP at the cap, hand-off sentence. |
| A specific/answerable billing question answered directly (BR5) | Yes | `answerable_billing_opener_proceeds`; `ProblemOpenerDetector.isOpener` requires opener phrasing, concrete anchor bypasses. |
| A human request is not intercepted (BR5) | Yes | `human_request_proceeds`; `ProblemOpenerDetector` ESCALATION_REQUEST short-circuit → PROCEED → escalation path. |
| Clarifying wording follows session language FR/EN (BR6) | Yes | `clarifyOrEscalate` resolves `AnswerLanguage` via `LanguageDetector`; `clarifyDirective()`/`handoffSentence()` per language; `ClarifyingQuestionAdapterTest.nullLanguageFallsBackToEnglish`. |
| No invented amount in a clarifying question (BR4 / DEC-002) | Yes | `clarify_voicing_an_amount_is_blocked`; `OutputGuardrail.check(question, [], language)` drops an amount-bearing clarify for the hand-off. |
| Works on web voice (streaming) and text (blocking) paths | Yes | Decorator implements both `ConverseUseCase` + `ConverseStreamUseCase`; `streaming_billing_opener_emits_clarify`, `streaming_non_opener_delegates`. |
| Configurable max clarifying questions (OQ-043-a, default 2) | Yes | `application.yml` `billing-clarify.max-questions:2`; `bound_is_configurable`, `disabled_when_max_non_positive`. |

## Test Evidence

- Developer tests (all green, full suite 751, 0 fail):
  - `BillingDiagnosticConversationServiceTest` (12): clarify, bound, configurable bound, disable,
    non-opener proceed, human-request proceed, anchored-opener proceed, clarify-answer proceed,
    DEC-002 amount block, streaming clarify, streaming proceed, telemetry.
  - `ClarifyingQuestionAdapterTest` (4): stripped question, no-RAG-context + clarify directive last,
    history reuse, null-language → English.
  - `AnswerLanguageTest` (+2): clarify directive one-question/no-figure, hand-off marker match.
  - `ConversationMemoryConfigWiringTest`: updated with a `ClarifyingQuestionGeneratorPort` bean —
    both configs still wire the single decorator per converse port.
- Missing tests: none blocking. (The provider adapters inherit `generateClarifyingQuestion` from the
  abstract base, covered once via `MistralAnswerAdapter`.)
- QA scenarios to run: FR + EN under-specified billing opener → one clarify; two openers → cap →
  advisor hand-off; `CONVERSATION_BILLING_CLARIFY_MAX_QUESTIONS=1` and `=0` behaviour; a concrete
  billing question answered directly; latency of the clarify turn vs a normal answer turn.

## Observability And Latency

- Relevant slices: LLM (`llm_wording` — the clarify call is timed there, bounded by the same timeout).
- OpenTelemetry traces: clarify call rides the existing LLM slice timing + correlation id.
- Metrics: new `voice_support.billing_clarify` counter — `event=asked` (streak count) /
  `event=cap_escalated`, tagged `language` + `channel`; satisfies US-043 analytics (clarify asked,
  per-conversation bound, escalated-vs-resolved via the count).
- Structured logs: `[BILLING-CLARIFY] event=… language=… count=… channel=…` (no PII, no amount).
- Missing: none required for this increment.
- Risk: low — the clarify replaces the answer LLM call on that turn, so no new unbounded cost.

## Security And Privacy

- Sensitive data risk: none — the clarify prompt carries no account/invoice data (no RAG context,
  no BSS on `/converse`); the LLM is instructed never to state an amount/date and the output is
  DEC-002-vetted.
- Identity/access risk: none new — the decorator does not touch identity/routing.
- Logging risk: none — telemetry logs only event/language/count/channel, never the transcript or an
  amount.

## Required Developer Actions

1. None (blocking list empty).

## Residual Risk If Accepted

- Memory-derived streak resets on an interleaved non-opener turn (by design).
- Pilot clarify improves retrieval/escalation context only, not amount accuracy (no live BSS).
- Per-sub-type clarify specialisation deferred (OQ-043-b).
