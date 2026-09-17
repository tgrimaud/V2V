# LLM Provider Tasks (Sprint 15)

Provider-agnostic LLM chat wiring (DEC-011). Embeddings always stay on Ollama (768d); these
tasks only select the **chat** provider via `voice-support.llm.provider`.

---

## TASK-BE-049 — OpenAI chat provider (`gpt-5`)

**Type:** Technical task · **Sprint:** 15 · **Status:** ✅ Validated (review 94/100 + E2E OK)
**Review:** `docs/qa/task-be-049-openai-provider-review.md` (2026-09-17, QA gate PASS, no blocking)

### E2E backend run — 2026-09-17 (real RAG turn via OpenAI provider)

Booted `LLM_PROVIDER=openai` (single JVM) against Dockerized Postgres pgvector + local Ollama
embeddings, `vector_store` populated from the 3 KB files. Two `POST /api/conversation/converse`
turns, both **HTTP 200**:

- **Billing** ("pourquoi ma facture peut augmenter") → **grounded** FR answer citing real KB content
  (3900, prorata, remises hors % d'augmentation), `confidence≈0.74`, ~2.28 s total.
- **Support** ("mon internet ne fonctionne plus") → **fail-closed escalation** (`low_confidence` +
  `escalation_context`) — correct guardrail behavior on insufficient grounding, not an OpenAI error.

Telemetry confirms the provider actually used: `slice=llm_wording provider=openai outcome=success
duration_ms≈1993/2094`, `[LANGUAGE]/[PROMPT]/[ANSWER] provider=openai`, `slice=retrieval
provider=pgvector ~175ms`. Per-provider tagging works → the benchmark (p50/p95 by provider) is
queryable with zero extra instrumentation.
**Branch:** `task/TASK-BE-049-openai-chat-provider` (off `feat/sprint-15-llm-providers`)

### Context

Mistral (`mistral-api`, default) and Ollama (`ollama`, local) are the two selectable LLM
wording providers. We received OpenAI access and want to benchmark **GPT (`gpt-5`)** against
Mistral for the voice wording step. The `AnswerGeneratorPort` seam (DEC-011) already supports
adding a provider with no domain change.

### Goal

Add `openai` as a third value of `voice-support.llm.provider`, built manually in `LlmConfig`
(the OpenAI auto-configurations are excluded), reusing the DEC-002 grounded voice prompt.

### Changes

- `pom.xml` — add `spring-ai-starter-model-openai` (Spring AI 1.0.0, already in the BOM).
- `VoiceSupportApplication` — exclude the 6 OpenAI auto-configs (chat, embedding, moderation,
  image, audio-speech, audio-transcription) so no OpenAI bean is auto-created; embeddings stay
  Ollama, STT/TTS stay on the voice runtime.
- `LlmConfig` — add `openai` to `SUPPORTED_PROVIDERS`; add a conditional `OpenAiChatModel` bean
  (`OpenAiApi.builder().baseUrl().apiKey().restClientBuilder()` + `OpenAiChatOptions` model +
  temperature) and a conditional `OpenAiAnswerAdapter` bean, mirroring Mistral/Ollama.
- `OpenAiAnswerAdapter` — thin subclass of `AbstractChatClientAnswerAdapter` (provider name
  `openai`, same grounded DEC-002 voice prompt with `{context}`).
- `application.yml` — `spring.ai.openai` section (`OPENAI_API_KEY`, `OPENAI_BASE_URL`,
  `OPENAI_CHAT_MODEL=gpt-5`, `OPENAI_CHAT_TEMPERATURE=1.0`, `OPENAI_REASONING_EFFORT=minimal`) +
  provider doc mentions `openai`.

### Notes / caveats

- **Temperature:** `gpt-5` accepts only the default temperature (1.0); a lower value is
  rejected with HTTP 400. Default is 1.0, overridable via `OPENAI_CHAT_TEMPERATURE` for models
  that allow tuning. (The other providers keep 0.2 for BUG-004 determinism.)
- The same provider HTTP read/connect timeouts (`voice-support.llm.*`) apply, so a slow/hung
  OpenAI call degrades to the sanitized 503 path like the other providers.
- Telemetry: `llm_first_token` / `llm_wording` slices are tagged `provider=openai`, so a
  per-provider latency comparison is queryable with no extra instrumentation.

### Acceptance

- `LLM_PROVIDER=openai OPENAI_API_KEY=… ` boots and answers a grounded `converse` turn in the
  customer's language; `LLM_PROVIDER` unset keeps Mistral as default.
- `mvn test` green (ArchUnit + hexagonal + `OpenAiAnswerAdapterTest`); zero new failures vs the
  branch base (the 10 pre-existing `RunKnowledgeBddTest` errors are unrelated).
- Adversarial code review ≥ 90%.

### Live smoke test — 2026-09-17 (Azure AI Foundry, OpenAI-compatible v1)

Endpoint is **Azure AI Foundry** (`*.services.ai.azure.com`) on its **OpenAI-compatible `/openai/v1`**
surface — not classic Azure OpenAI. It speaks the OpenAI protocol, so the existing `OpenAiApi`
wiring works unchanged: `Authorization: Bearer <key>`, path `/v1/chat/completions`, **no
`api-version`**. Config: `OPENAI_BASE_URL=https://Ai4cc-POC-SWD.services.ai.azure.com/openai` (root
**without** `/v1`; Spring AI appends `/v1/chat/completions`), `OPENAI_CHAT_MODEL=gpt-5`.

Direct `curl` to `.../openai/v1/chat/completions` → **HTTP 200**, model resolved to
`gpt-5-2025-08-07`, valid grounded FR answer, Azure content filters "safe".

- ⚠️→✅ **Latency (voice-critical), fixed:** `gpt-5` is a **reasoning** model. At the default effort
  a trivial turn spent **128 reasoning tokens / total ≈ 2.6 s**. Setting **`reasoning_effort=minimal`**
  drops it to **0 reasoning tokens / ≈ 0.95 s** (measured on this endpoint). Spring AI 1.0.0
  `OpenAiChatOptions.Builder.reasoningEffort(String)` exists, so this is now **wired**: default
  `minimal` (voice-first), `OPENAI_REASONING_EFFORT` overrides (minimal|low|medium|high), and blank
  disables it so a non-reasoning model (gpt-4o) is not rejected with a 400.
- Auth confirmed as Bearer (API key). Temperature left at the gpt-5 default (1.0).

### How to test live

```bash
cd backend
export OPENAI_API_KEY=sk-...            # your new key
export LLM_PROVIDER=openai              # select the OpenAI provider
# optional: export OPENAI_CHAT_MODEL=gpt-5
mvn spring-boot:run                     # needs Ollama for embeddings + Postgres for RAG
# then, in another shell (api-key gate open when CONVERSATION_API_KEY is empty):
curl -s localhost:8080/api/conversation/converse \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"t1","transcript":"Pourquoi ma facture a augmenté ce mois-ci ?","language":"fr"}'
```
