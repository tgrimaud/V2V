# Adversarial Code Review — TASK-BE-049 (OpenAI chat provider, gpt-5)

Reviewed: 2026-09-17 · Branch: `task/TASK-BE-049-openai-chat-provider` · Base: `feat/restart-from-scratch`

## Verdict

**Proceed.** Clean, consistent provider-wiring change behind the existing `AnswerGeneratorPort`
seam, with no domain change, inherited observability, and a live-validated endpoint. No blocking
findings.

## Satisfaction Score

Score: **94/100**
QA gate: **Pass**

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Low-Med | DEC-002 system prompt now **triplicated** across `MistralAnswerAdapter`, `OllamaAnswerAdapter`, `OpenAiAnswerAdapter` (byte-identical). A DEC-002 wording change must touch 3 files → drift risk (the `OutputGuardrail` matches hand-off wording). | 3 identical `SYSTEM_PROMPT` blocks | Extract a shared voice-prompt constant (touches all 3 adapters — a small follow-up refactor, out of this ticket's scope). Pre-existing pattern, followed here for consistency. |
| Low | No unit test on the `LlmConfig` OpenAI bean wiring / `reasoning-effort` blank-guard branch. | `openAiChatModel(...)` `if (!isBlank) reasoningEffort(...)` | Config `@Bean` methods are untested for Mistral/Ollama too (no `@SpringBootTest`); the branch is trivial. Optional: a direct-call unit asserting the built options, or a `@SpringBootTest(properties=...)` context smoke. Accepted as low-risk. |
| Low | `OPENAI_BASE_URL` double-path footgun: Spring AI appends `/v1/chat/completions`, so a base-url that already includes it breaks. | `OpenAiApi.builder().baseUrl(baseUrl)` | Documented in `application.yml` + ticket ("root only, without /v1"). Operational note; acceptable. |
| Low | Default `reasoning-effort=minimal` sent to any model; a non-reasoning model (e.g. `gpt-4o`) would reject the param with a 400. | `reasoning-effort: ${OPENAI_REASONING_EFFORT:minimal}` | Documented: set `OPENAI_REASONING_EFFORT=` (empty) for non-reasoning models; blank-guard then omits it. Acceptable. |

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|
| `openai` selectable via `voice-support.llm.provider`, no domain change | ✅ | `SUPPORTED_PROVIDERS` + `@ConditionalOnProperty` beans; domain unchanged (adapter only) |
| Mistral stays the default | ✅ | `mistral-api` `matchIfMissing=true`; openai beans inactive unless selected |
| Embeddings stay on Ollama (768d) | ✅ | `OpenAiEmbeddingAutoConfiguration` excluded; no OpenAI embedding bean |
| Grounded DEC-002 voice prompt | ✅ | `OpenAiAnswerAdapterTest.usesGroundedDec002Prompt` |
| Boots + answers a grounded turn on the real endpoint | ✅ (endpoint) | Live smoke test HTTP 200, gpt-5→gpt-5-2025-08-07, valid FR answer (ticket § Live smoke test). Full backend E2E: next step. |
| `mvn test` green, no new failures vs base | ✅ | OpenAI 2/2 + ArchUnit/hexagonal 16/16; 10 `RunKnowledgeBddTest` errors pre-exist on mainline (unrelated) |

## Test Evidence

- Developer tests: `OpenAiAnswerAdapterTest` (provider name + grounded prompt); ArchUnit + hexagonal green.
- Missing tests: none blocking. Optional `LlmConfig` reasoning-effort branch test (low ROI).
- QA scenarios to run: full backend `converse` turn with `LLM_PROVIDER=openai` (E2E, next step).

## Observability And Latency

- Relevant slices: `llm_first_token`, `llm_wording` (+ answer length/language/prompt-size metrics).
- OpenTelemetry traces/metrics: **inherited** from `AbstractChatClientAnswerAdapter`, tagged
  `provider=openai` via `providerName()` → per-provider p50/p95/p99 queryable with zero extra code.
- Structured logs: `[TELEMETRY]` line with slice/provider/outcome (existing).
- Missing: none for this change.
- Risk: with `reasoning_effort` above `minimal`, gpt-5 first-token can approach `stream-timeout-ms`;
  default `minimal` keeps it ~0.95 s (measured). No action needed at the default.

## Security And Privacy

- Sensitive data risk: none new; no PII in prompt wiring.
- Identity/access risk: API key from `OPENAI_API_KEY` (env); `.env` is gitignored; no secret committed.
- Logging risk: key never logged; smoke-test output was redacted.

## Required Developer Actions

1. None blocking. (Optional follow-ups: extract shared voice prompt; add a config-branch test.)

## Residual Risk If Accepted

- Prompt duplication across 3 adapters (drift risk if DEC-002 wording changes) — low, tracked as a
  follow-up refactor.
- Full backend E2E (RAG-grounded turn via the OpenAI provider) not yet executed at review time — run
  as the immediate next step before declaring the provider production-usable for the pilot.
