# Adversarial code review — TASK-BE-070 (US-043 increment D)

**Scope:** billing clarify increment D — broaden `ProblemOpenerDetector` billing path + turn the
targeted clarify into one short question at a time (deterministic, no LLM, no multi-turn state).
**Branch:** `task/TASK-BE-070-billing-clarify` (off `feat/sprint-16-billing-clarify`).
**Reviewed changes:** `ProblemOpenerDetector`, `GuardrailMessages.problemOpenerClarify`,
`InputGuardrail.problemOpenerDecision`; tests `ProblemOpenerDetectorTest`, `InputGuardrailTest`,
`ConversationGroundingSteps` + `conversation-grounding.feature`.
**Date:** 2026-10-08.

## Verdict

Proceed.

## Satisfaction Score

Score: 93/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | Full backend suite green (746 tests, 0 failures); DEC-002 and ladder invariants locked by tests | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low | The amount anchor is deliberately narrow (digit or spelled "euro(s)"); other spelled numbers ("dix euros" without the word euro → caught by `euros`; but "trois" alone is not an anchor) and payment-mechanic phrasings still clarify | `CONCRETE_BILLING_ANCHOR = ([0-9]|\b(euro|euros)\b)` | Accept for D; payment-mechanic widening is explicitly deferred to TASK-BE-071 (increment C) |
| Low | Behavior change: billing problem-openers that carry only a weak interrogative (e.g. "Pourquoi ai-je un problème de facturation ?", "How do I fix the problem with my bill?") now CLARIFY instead of being answered. This intentionally relaxes the BUG-025 "any marker bypasses" rule **for billing openers only** | `classify()` billing branch; updated `does_not_clarify_specific_problem_question` + new `flags_underspecified_billing_opener_with_weak_marker` | Accept — it is the exact user-reported fix; documented in the ticket and here |
| Info | Telemetry reason value changed `problem_opener` → `problem_opener_billing` / `problem_opener_general` (low-cardinality, 2 values) | `InputGuardrail.problemOpenerDecision`; `recordGuardrailBlock(verdict, reason)` on both sync + streaming paths | If any pilot dashboard panel filters on the literal `problem_opener`, update it to the two new values |

## Story Coverage

| Acceptance criterion (US-043 / TASK-BE-070) | Covered? | Evidence |
|---|---|---|
| Under-specified billing problem → single short clarifying question (FR/EN), not a 4-option list, not a bill enumeration | Yes | `InputGuardrailTest.clarifies_underspecified_fr/en_billing_opener`, `billing_clarify_is_one_question_without_amount` (exactly one `?`); `GuardrailMessages` rewritten to one clause |
| Specific, answerable billing question still answered (BUG-025 invariant for anchored/answerable turns) | Yes | `does_not_clarify_specific_problem_question` ("a augmenté de 10 euros" PASS; non-billing opener+marker PASS); detector `ignores_specific_question` (digit + "cinq euros" anchors) |
| Explicit advisor request / off-topic / unsafe not intercepted (ladder order preserved) | Yes | `opener_does_not_soften_unsafe_request`, `opener_with_advisor_request_reaches_pipeline` (unchanged, still green); ladder order in `InputGuardrail.check` untouched |
| Clarify never contains an amount/price (DEC-002) | Yes | `billing_clarify_is_one_question_without_amount` asserts no digit; BDD step asserts `.*\d.*` absent; wording is canned |
| Clarify telemetry present and asserted (billing countable) | Yes | reason `problem_opener_billing` / `problem_opener_general` asserted in `opener_clarify_carries_reason` + `general_opener_clarify_carries_reason`; flows to `GUARDRAIL_BLOCK` counter tag |
| `mvn test` green incl. ArchUnit; pure domain, no Mockito, GIVEN/WHEN/THEN | Yes | 746 tests / 0 failures; domain classes stay Spring-free; manual fakes only |

## Test Evidence

- Developer tests: `ProblemOpenerDetectorTest` (broadened billing + preserved bypass + escalation + null), `InputGuardrailTest` (FR/EN clarify, reason tags, DEC-002 one-question, preserved PASS, ladder), BDD `conversation-grounding.feature` (+ one new under-specified-opener scenario).
- Missing tests: none blocking. (Voice-agent Behave is unaffected — backend-only change.)
- QA scenarios to run: live FR/EN voice turn with a vague billing opener → hear one short question, no amount; a billing turn with a number → answered directly; "je veux un conseiller" → escalation, not clarify.

## Observability And Latency

- Relevant slices: backend guardrail stage (pre-retrieval). No new latency surface (deterministic regex, no LLM/retrieval on the clarify turn).
- OpenTelemetry traces: unchanged span structure; clarify remains a guardrail-block turn (no retrieval/LLM).
- Metrics: `GUARDRAIL_BLOCK` counter now carries `reason=problem_opener_billing|problem_opener_general` + `verdict=clarify` → billing clarify rate is directly countable (US-043 analytics).
- Structured logs: `[GUARDRAIL] verdict=clarify reason=… channel=… correlation_id=…` emitted on both sync and streaming paths; no PII (canned wording, no user text logged).
- Missing: none for this increment.
- Risk: low — a clarify turn skips retrieval + LLM, so it is faster than a normal turn (no SLO regression).

## Security And Privacy

- Sensitive data risk: none — clarify wording is canned, states no amount (DEC-002), logs no user text.
- Identity/access risk: none — no identity or BSS path touched.
- Logging risk: none — only verdict/reason/correlation id logged.

## Required Developer Actions

1. None blocking. Optional: if a pilot telemetry dashboard filters on the literal `problem_opener`, update it to the two topic-tagged values.

## Residual Risk If Accepted

- The deliberate billing broadening may clarify a small number of billing problem-openers that a user considered "obvious"; mitigated by the single short question (one turn) and bounded by the specific-amount anchor. Payment-mechanic answerability and multi-turn diagnostic depth are deferred to TASK-BE-071 (increment C).
