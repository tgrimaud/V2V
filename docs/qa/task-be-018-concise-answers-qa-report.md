# QA Functional And Latency Report — TASK-BE-018 (Concise Voice-First Answers)

## Executive Summary

- **Overall readiness:** **Go for pilot integration** on the answer-quality/latency lever.
  A configured sentence budget shortens grounded answers substantially with **no
  functional regression** (grounding, language, hand-off all preserved).
- **Main blockers:** none.
- **Residual risks:** (1) latency evidence is measured on the **backend lever**
  (`answer_chars` + `llm_wording`), not on end-to-end mouth-to-ear — the TTS/channel-egress
  slices are downstream and scale with answer length but are not yet instrumented
  (TASK-WEB-014); (2) small warm-only sample (n=8 grounded / 10 total per run) — the
  **direction is unambiguous** (every question shorter or equal) but p95 is indicative,
  not an SLO; (3) the cap is advisory (prompt-level) so extreme prompts could still exceed
  it — none observed.

## Scope Tested

- **Story:** TASK-BE-018 — cap voice answers to a configurable sentence budget to cut TTS
  synthesis time without weakening grounding (DEC-002 / BUG-004).
- **Channels:** `api` (sync `POST /api/conversation/converse`, ADR-0021 contract). The
  lever is channel-agnostic (prompt-level); WebRTC/batch benefit downstream.
- **Providers:** Mistral `mistral-small-latest` (live), Ollama `nomic-embed-text` embeddings
  (live), pgvector 5433 (**10 163 KB chunks**: `csv-article` 4 996, `csv-article-fr` 5 128,
  `markdown` 39).
- **Environment:** BE-018 jar on `:8081`, warm (single run per arm), no cache priming beyond
  natural warm-up, correlation ids per request.
- **Automation:** backend unit/component + Cucumber BDD (`mvn test` **229 green**, ArchUnit OK).

## Functional Results

| Area | Status | Evidence | Notes |
|---|---|---|---|
| Grounded answer still voiced (budget on) | ✅ Pass | Live A/B: 8/8 grounded turns carry confidence at budget=3 | No BUG-004 regression |
| BUG-004 greeting case ("Bonjour, j'ai un problème avec ma connexion internet") | ✅ Pass | Answered, grounded (conf 0.85), 224 chars at budget=3 | Was the BUG-004 trigger; still answers |
| Answer language follows question (FR→FR, EN→EN) | ✅ Pass | 10/10 language-correct at budget=3 **and** budget=0 | ADR-0031 preserved |
| Off-topic refusal, correct language, no confidence | ✅ Pass | 2/2 refused (FR + EN), confidence=null | Guardrail path unchanged |
| Hand-off on unusable evidence unchanged by budget | ✅ Pass | BDD `answer-concision.feature` (unusable evidence → non-grounded + advisor) | Budget does not alter escalation |
| Concision instruction present + in answer language when budget set | ✅ Pass | BDD (real adapter + capturing ChatModel): "3 sentence(s)/phrase(s) maximum" in EN/FR, ordered before the language directive | Contract net |
| Concision instruction absent when budget disabled | ✅ Pass | BDD disabled scenario; live budget=0 run | 0 disables cleanly |

## Latency Results

Backend answer-shaping lever, warm, channel `api`, Mistral `mistral-small-latest`, n per arm
as noted. `answer_chars` = spoken answer length (`voice_support.answer_chars`); `llm_wording`
= LLM generation slice (`voice_support.slice`).

| Metric (grounded, n=8) | p50 | p95 | max | mean | Warm/Cold |
|---|---:|---:|---:|---:|---|
| **answer_chars — budget=3** | 286 | 336 | 352 | 280 | Warm |
| **answer_chars — budget=0 (disabled)** | 426 | 899 | 910 | 517 | Warm |
| **Reduction** | **−33 %** | **−63 %** | −61 % | **−46 %** | |
| **llm_wording ms — budget=3** | 846 | 2033 | 2491 | — | Warm |
| **llm_wording ms — budget=0** | 1200 | 3100 | 3682 | — | Warm |
| **Reduction** | **−30 %** | **−34 %** | −32 % | | |

Per-question grounded answer length (budget=3 → budget=0): every turn shorter or equal.
Largest collapses: "Why is my bill higher…" 295→878 (Δ+583 when disabled), "How do I set up
my new router?" 352→910 (Δ+558), "Comment résilier…" 226→634 (Δ+408).

| Slice | Status | Notes |
|---|---|---|
| LLM wording | ✅ Measured | see table; shorter output → faster generation |
| Answer length (proxy for TTS cost) | ✅ Measured | `answer_chars` p50 286 vs 426 |
| TTS synthesis / batch TTFA | ⚠️ Not measured here | Downstream (voice-agent); scales with answer length — the ≈14 s batch TTFA driver is answer size, so a −33 %/−63 % length cut directly reduces it |
| Channel egress / mouth-to-ear | ⚠️ Not measured | Requires TASK-WEB-014 instrumentation (ADR-0029 gate) |

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| `AnswerLanguage.concisionDirective` | ✅ | Per-language cap, `%d`, disabled ≤0 | — |
| `AbstractChatClientAnswerAdapter` prompt assembly | ✅ | Concision appended before the language directive (recency preserved); no post-hoc truncation | — |
| `LlmConfig` wiring | ✅ | `voice-support.llm.max-answer-sentences` (default 3, 0 disables) into both adapters | — |
| `BackendTelemetry.recordAnswerLength` | ✅ | `voice_support.answer_chars` p50/p95/p99 + `[ANSWER]` log (length only) on sync + streaming | — |
| OutputGuardrail / escalation | ✅ | Unchanged; hand-off markers intact | — |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Low | Streaming vs sync `answer_chars` measured slightly differently (streaming counts un-stripped tokens) | ≤ few chars on percentiles | BE (accepted, adversarial review) |
| Info | Warm-only, n=8 grounded per arm | p95 indicative, not an SLO | QA — enlarge sample at pilot latency campaign |
| Info | TTS/mouth-to-ear not directly measured | latency claim is on the backend lever + proxy | TASK-WEB-014 |

## Open Questions

- **Product:** confirm the default budget (3 sentences) is the right voice UX target, or
  tune per domain (billing vs technical) — current live sample reads natural at 3.
- **Architecture:** none (prompt-level lever, no boundary change).
- **Technical:** schedule TTS-side / mouth-to-ear confirmation under TASK-WEB-014.

## Recommendation

- **Go / No-go:** **Go.** Functional non-regression proven live (grounding, language,
  escalation), and the budget delivers a large, consistent answer-length and LLM-latency
  reduction. Automated regression net in place (`mvn test` 229 green incl. BDD
  `answer-concision.feature`).
- **Required fixes before pilot:** none blocking. Before any **latency SLO claim**, fold in
  TTS/channel-egress measurement (TASK-WEB-014) and enlarge the sample; keep budget=3 as the
  default, env-tunable via `LLM_MAX_ANSWER_SENTENCES`.
