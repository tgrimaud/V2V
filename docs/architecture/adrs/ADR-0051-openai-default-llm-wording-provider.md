# ADR-0051: OpenAI `gpt-5` Is The Default LLM Wording Provider

## Status

Accepted (2026-09-17) — refines ADR-0006; the LLM benchmark ADR-0045 stays Proposed.

## Context

The answer engine's chat (wording) LLM sits behind a replaceable provider port
(`AnswerGeneratorPort` / `StreamingAnswerGeneratorPort`, DEC-005/DEC-011, ADR-0026). Until
Sprint 15 the default provider was **Mistral** (`mistral-small-latest`, ADR-0006), with Ollama
as the local/offline alternative and OpenAI planned but unvalidated (DEC-011 — "live validation
gated on OpenAI credentials, not yet available").

In Sprint 15, OpenAI credentials (an Azure AI Foundry OpenAI-compatible `/openai/v1` endpoint)
became available. TASK-BE-049 added OpenAI (`gpt-5`) as a third selectable provider behind the
existing port and validated it **live** (HTTP 200, model resolved `gpt-5 → gpt-5-2025-08-07`,
Bearer auth, no `api-version`) and **end-to-end** (a full RAG-grounded FR billing turn, with
`reasoning_effort=minimal` cutting a trivial turn from ~2.6 s to ~0.95 s). The user then decided
to make OpenAI the default (TASK-BE-050).

## Decision

**OpenAI `gpt-5` is the default LLM wording provider.** `voice-support.llm.provider` defaults to
`openai` (`application.yml` `${LLM_PROVIDER:openai}`; `LlmConfig` `@Value(":openai")`; the
`matchIfMissing=true` conditional is on the OpenAI beans). Mistral (`mistral-api`) and Ollama
(`ollama`) remain fully selectable via `LLM_PROVIDER` with no code change.

Scope is the **chat/wording** model only. Embeddings stay on Ollama `nomic-embed-text` (768 dim,
ADR-0006/ADR-0039); STT/TTS stay on the voice runtime (Gradium). DEC-002 grounding is unchanged:
the LLM only rephrases confirmed evidence; amounts stay deterministic.

## Consequences

- **Deployment (mandatory):** any environment that relies on the default (does not set
  `LLM_PROVIDER=mistral-api`) **must** provide `OPENAI_API_KEY` and, for the Azure Foundry
  endpoint, `OPENAI_BASE_URL` (root without `/v1`), or the first LLM call 401s / hits public
  `api.openai.com`. Wired via TASK-INFRA-019 (`.env.example`, Ansible template + vault, runbooks).
- **Pilot source-of-truth (interim):** the pilot deploy **explicitly pins `LLM_PROVIDER=mistral-api`**
  (the validated pilot path) until an OpenAI pilot cost/latency benchmark (ADR-0045 / TASK-BE-033)
  justifies switching. OpenAI is the application/local default and a deploy option; switching the
  pilot to OpenAI is then a config change, not a code change.
- **Latency:** `gpt-5` is a reasoning model; `reasoning_effort=minimal` is the default lever to keep
  it near the mouth-to-ear budget. A non-reasoning model (e.g. `gpt-4o`) needs
  `OPENAI_REASONING_EFFORT=` (empty) so the param is omitted.
- **Temperature:** `gpt-5` accepts only `temperature=1.0`; the value stays configurable for models
  that allow tuning.
- Per-provider observability (`llm_wording` / `llm_first_token` tagged `provider=openai|mistral-api|ollama`)
  makes the Mistral-vs-OpenAI benchmark (ADR-0045) queryable with no extra code.

## Alternatives Considered

- **Keep Mistral as the default (ADR-0006 unchanged):** rejected as the code default per the user's
  decision, but **retained as the pinned pilot provider** until the benchmark decides.
- **Make OpenAI default only in deploy config, not in code:** rejected — the code default should
  reflect the intended primary provider; deploy explicitly pins the interim pilot choice instead.
- **Wait for the full ADR-0045 benchmark before flipping any default:** rejected — the flip is a
  cheap, reversible config default behind the port; the benchmark still governs the *pilot* choice.

## Related Documents

- ADR-0006 (chat/embedding split — default-provider clause superseded here)
- ADR-0045 (LLM provider/model benchmark — still Proposed, TASK-BE-033)
- ADR-0026 (replaceable LLM port), ADR-0029 (latency criterion), DEC-011 (provider strategy)
- `product-backlog/tasks/llm-provider-tasks.md` (TASK-BE-049 / TASK-BE-050)
- `product-backlog/tasks/review-2026-09-17-remediation-tasks.md` (TASK-DOC-008)
