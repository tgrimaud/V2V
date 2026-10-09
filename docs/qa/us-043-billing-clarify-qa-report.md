# QA Functional And Latency Report — US-043 (billing clarify, increments D + C)

Date: 2026-10-08 · Branch: `feat/sprint-16-billing-clarify` · Tickets: TASK-BE-070 (D), TASK-BE-071 (C)

## Executive Summary

- **Overall readiness:** GO for functional acceptance of US-043 on the backend conversation flow.
  All six product-acceptance scenarios are automated and green; the full backend suite is **758
  tests, 0 failures** (incl. ArchUnit and the 48-scenario Cucumber BDD suite).
- **Main blockers:** none.
- **Residual risks:** (a) latency not measured here — this change has no live STT/LLM/TTS in the
  test environment, so the voice-SLO slices must be confirmed on the pilot with a real provider;
  (b) on the pilot `/converse` has no live BSS, so clarify improves retrieval/escalation context,
  not amount accuracy (DEC-002 unchanged); (c) memory-derived clarify streak resets on an
  interleaved non-opener turn (by design, ADR-0056).

## Scope Tested

- **Epics / stories:** EPIC-005 / US-043 (ask a clarifying question before answering a billing
  problem), via TASK-BE-070 (deterministic single clarify, one question at a time) and TASK-BE-071
  (bounded, LLM-worded, configurable clarify dialogue).
- **Channels:** backend conversation flow for both the blocking (`/converse`, text) and streaming
  (`/converse-stream`, web voice) paths — validated through the use-case ports, not the live media
  layer.
- **Providers / fakes:** fake converse delegates, fake `ClarifyingQuestionGeneratorPort`, with the
  **real** `ProblemOpenerDetector`, `OutputGuardrail`, `LanguageDetector`, `ConversationMemoryPort`
  (in-memory adapter) and `BackendTelemetry` (SimpleMeterRegistry). No live LLM/STT/TTS.
- **Environment:** `mvn -o test` (JUnit 5 + Cucumber-JVM), no DB / no Ollama (no `@SpringBootTest`).

## Functional Results

| Area (US-043 acceptance) | Status | Evidence | Notes |
|---|---|---|---|
| Under-specified billing problem → one short question, no enumeration (BR1/BR2/BR4) | ✅ Pass | `billing-clarify.feature` S1; `BillingDiagnosticConversationServiceTest.first_billing_opener_asks_llm_clarify`; D: `conversation-grounding.feature` "under-specified billing opener with a weak marker is clarified" | Clarify produced before any retrieval. |
| Clarifying dialogue is bounded → then answer-or-advisor, no further question (BR3) | ✅ Pass | `billing-clarify.feature` S2; `bounds_clarifies_then_escalates`, `bound_is_configurable` | Cap → advisor hand-off with collected context (ADR-0019). |
| Specific/answerable billing question answered directly (BR5) | ✅ Pass | `billing-clarify.feature` S3; `answerable_billing_opener_proceeds`; D: `conversation-grounding.feature` "specific billing problem still reaches retrieval" | Amount-anchored opener bypasses the clarify. |
| Explicit human request not intercepted (BR5) | ✅ Pass | `billing-clarify.feature` S4; `human_request_proceeds` | Flows to the escalation path, not the clarify flow. |
| Clarifying wording follows session language FR/EN (BR6) | ✅ Pass | `billing-clarify.feature` S5; `ClarifyingQuestionAdapterTest.nullLanguageFallsBackToEnglish`; `AnswerLanguageTest` clarify directive | Decorator resolves `AnswerLanguage` and passes it to the generator. |
| No invented amount in a clarifying question (BR4 / DEC-002) | ✅ Pass | `billing-clarify.feature` S6; `clarify_voicing_an_amount_is_blocked` | An amount-bearing clarify is DEC-002-vetted out → safe hand-off. |
| Configurable max questions (OQ-043-a, default 2; `<=0` disables) | ✅ Pass | `bound_is_configurable`, `disabled_when_max_non_positive`; `application.yml` `billing-clarify.max-questions:2` | Env `CONVERSATION_BILLING_CLARIFY_MAX_QUESTIONS`. |
| Streaming path parity (web voice) | ✅ Pass | `streaming_billing_opener_emits_clarify`, `streaming_non_opener_delegates` | Clarify emitted as one chunk; non-opener delegates to the stream. |

## Latency Results

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| LLM wording (clarify turn) | n/a | n/a | n/a | 0 | n/a | **Not measured in this environment** — no live LLM. The clarify call is timed on the existing `llm_wording` slice via `BackendTelemetry.time(...)` and bounded by the same timeout as a normal answer; a clarify turn runs **no retrieval**, so it should be ≤ a normal answer turn. Measure on the pilot. |
| Channel ingress / EOT / STT / TTS / egress | — | — | — | 0 | — | Not affected by this backend change; measured on the voice runtime (TASK-WEB / streaming latency report). |

Latency verdict: **not yet measurable** for this story in the unit/BDD environment (deterministic
fakes). The clarify turn adds no retrieval and reuses the bounded `llm_wording` budget, so it is not
expected to regress the voice SLO; this must be confirmed with a live provider during pilot latency
runs (p50/p95/p99 of a clarify turn vs a normal answer turn).

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| `ProblemOpenerDetector` (trigger) | ✅ | Deterministic, accent-folded, word-boundary; billing opener vs anchored question; escalation short-circuit | — |
| `BillingDiagnosticConversationService` (decorator) | ✅ | Memory-derived streak, PROCEED/ASK_CLARIFY/ESCALATE_AT_CAP, both converse ports | — |
| `ClarifyingQuestionGeneratorPort` + LLM adapter | ✅ | No-RAG ask-one-question prompt, clarify directive recency-last, DEC-002-vetted | — |
| `OutputGuardrail` (DEC-002 on clarify) | ✅ | Empty-evidence check drops amount-bearing clarify | — |
| Observability | ✅ | `voice_support.billing_clarify` (asked/cap_escalated, tags language+channel), clarify timed on `llm_wording` | Confirm meter cardinality on the pilot collector |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Low | Latency of a clarify turn not measured (no live provider in test env) | Pilot-readiness evidence incomplete for the voice SLO | QA (pilot run) |
| Low | Pilot clarify improves retrieval/escalation context only, not amounts (no live BSS) | Expected per US-043 scope; DEC-002 unchanged | Product / OQ-002 |
| Low | Per-sub-type clarify (increase / unknown charge / promo expiry) not specialised | Single generic clarify prompt | Product / OQ-043-b |

## Open Questions

- **Product:** OQ-043-b (configurable billing sub-types for the clarify) — still open.
- **Architecture:** OQ-043-c resolved by ADR-0056; OQ-002 (live BSS feeding the collected context)
  remains for the post-pilot increment.
- **Technical:** confirm the clarify-turn latency distribution on the pilot vs a normal answer turn.

## Recommendation

- **Go / No-go:** **GO** for functional acceptance of US-043 (D + C) on the backend.
- **Required fixes before pilot:** none functional. Before claiming a voice-SLO pass, run the pilot
  latency measurement for a clarify turn (live LLM) and record p50/p95/p99 alongside a normal answer
  turn.
