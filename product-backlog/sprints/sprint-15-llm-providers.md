# Sprint 15 — LLM Providers / Benchmarking

## Sprint Objective

Make the **LLM chat provider** a first-class, swappable choice so several models can be
benchmarked for the voice wording step (latency, quality, cost) **without any domain
change**. The product core stays provider-agnostic through the existing
`AnswerGeneratorPort` / `StreamingAnswerGeneratorPort` seam (DEC-011): a provider is
selected by `voice-support.llm.provider` and built manually in `LlmConfig`.

Embeddings **always stay on Ollama** (`nomic-embed-text`, 768d) — this sprint only touches
the **chat** provider. OpenAI STT/TTS (if ever adopted) stay on the **voice runtime**, not
the backend.

## Scope

- **TASK-BE-049 — OpenAI chat provider (`gpt-5`).** ✅ **Done (merged 2026-09-17).** `openai` is a
  third selectable provider behind the existing port, mirroring the Mistral/Ollama wiring.
  Live-validated (Azure AI Foundry OpenAI-compatible v1 endpoint) + full backend E2E RAG turn;
  adversarial review 94/100; `reasoning_effort=minimal` wired as the voice-latency lever.

### Follow-ups (candidate, not yet ticketed)

- Provider benchmark harness: per-provider p50/p95 `llm_first_token` / `llm_wording` and a
  small grounded-answer quality sample (uses the `provider` telemetry tag already emitted).
- OpenAI STT/TTS or Realtime evaluation on the **voice runtime** (separate track).

## Definition of Done (per ticket)

- Provider selectable via `LLM_PROVIDER=openai` with **no domain change**. (Original DoD kept
  Mistral as the default; **superseded during the sprint by TASK-BE-050** — OpenAI became the
  default, ADR-0051. Mistral/Ollama stay selectable; the pilot deploy pins `mistral-api`.)
- `mvn test` green (ArchUnit + hexagonal + unit); no new failures vs the branch base.
- Adversarial code review ≥ 90% before QA acceptance.
- Docs updated (`application.yml` provider doc + README env vars) in the same change.
- Merge only on the user's explicit request (ticket → sprint via `--no-ff`).

## Status

✅ **Done (closed 2026-09-17)** — merged into `feat/restart-from-scratch` (`--no-ff`). Delivered
TASK-BE-049 (OpenAI `gpt-5` as a third selectable LLM chat provider behind the existing port,
live + E2E validated, adversarial review 94/100, `reasoning_effort=minimal` voice-latency lever)
and TASK-BE-050 (OpenAI made the **default** provider). Mistral/Ollama still selectable via
`LLM_PROVIDER`. Note: environments relying on the default must set `OPENAI_API_KEY`
(+ `OPENAI_BASE_URL` for the Azure Foundry endpoint).

> Note: `feat/restart-from-scratch` currently carries **10 pre-existing errors** in
> `RunKnowledgeBddTest` (Cucumber steps still `PendingException`, WIP knowledge feature).
> They are unrelated to this sprint; BE-049 introduces zero new failures. Track separately.
