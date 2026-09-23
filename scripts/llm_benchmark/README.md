# LLM provider/model benchmark (TASK-BE-033 / ADR-0045)

Data-driven spike that measures each chat-LLM candidate on the **backend first-token**
slice — the largest remaining reducible slice of the ADR-0029 latency gate after
TASK-WEB-035 (STT tail) and TASK-WEB-036 (top-k 8→5, which showed the LLM's
time-to-first-token is ~87 % of `backend_first_token`). Scopes ADR-0029 **Direction A**
(cascade chat LLM), **not** Direction B (Realtime speech-to-speech).

The provider stays behind the replaceable `AnswerGeneratorPort` / `StreamingAnswerGeneratorPort`
(ADR-0026); this spike **measures**, it does not migrate the default.

## Candidates (ADR-0045)

1. `mistral-small` — `mistral-small-latest` (current baseline, EU, already wired).
2. `mistral-large` — `mistral-large-latest` (same EU residency, TTFT vs quality).
3. `ollama` — a co-located instruct model (no cloud hop / no chat egress).
4. `openai-gpt-4o-mini` — `gpt-4o-mini` (fast TTFT, **US** residency — OQ-009 compliance).

## What is measured

Text-in through the guarded `POST /api/conversation/converse-stream` path (real retrieval +
guardrails, no STT/TTS noise), on the shared billing fixture set (`billing_fixtures.json`,
the same 5 FR questions as the TASK-WEB-036 top-k A/B so numbers stay comparable):

- `llm_first_token` + `backend_first_token` **p50/p95** (server-authoritative from `[TELEMETRY]`
  when a log is supplied; client time-to-first-chunk otherwise, as a proxy including the network hop).
- **grounded rate** + **mean confidence** (from the terminal `done` SSE event).
- **DEC-002 heuristic:** count of euro-amount-like mentions per answer, flagged for manual
  adjudication (no fabricated amounts).
- **cost / residency / egress** metadata per candidate (recorded in `compare.py`, not measured).

## Run

The backend selects the provider/model at **startup** (`LLM_PROVIDER` + model env vars), so run
one candidate, restart the backend for the next, then merge. Each candidate is warm + isolated.

**Prereqs:** Postgres/pgvector up with the KB synced, Ollama up for embeddings
(`nomic-embed-text`, 768d), a built jar (`cd backend && mvn -q -DskipTests package`), and provider
creds in the repo-root `.env` or the env.

### One command per candidate (recommended)

`run_local_candidate.sh` boots the jar with the chosen provider, waits for readiness, runs the
harness against the backend's own log (server `[TELEMETRY]` slices), then stops it. It auto-detects
a JDK (`$JAVA_HOME` → macOS `java_home` → Maven's runtime) and sources the repo-root `.env`.

```bash
# EU baseline + large
scripts/llm_benchmark/run_local_candidate.sh mistral-small mistral-api mistral-small-latest \
    MISTRAL_CHAT_MODEL=mistral-small-latest
scripts/llm_benchmark/run_local_candidate.sh mistral-large mistral-api mistral-large-latest \
    MISTRAL_CHAT_MODEL=mistral-large-latest LLM_TIMEOUT_MS=30000 LLM_STREAM_TIMEOUT_MS=30000

# Co-located Ollama — RAISE the embedding/retrieval budgets: chat + embeddings share one Ollama,
# so a model swap can exceed the 5 s embedding default and error the turn (see Gotchas).
scripts/llm_benchmark/run_local_candidate.sh ollama-llama31-8b ollama llama3.1:8b \
    OLLAMA_CHAT_MODEL=llama3.1:8b EMBEDDING_TIMEOUT_MS=30000 RETRIEVAL_TIMEOUT_MS=35000 \
    LLM_TIMEOUT_MS=60000 LLM_STREAM_TIMEOUT_MS=60000

# Merge into the ADR-0045 comparison table:
python3 scripts/llm_benchmark/compare.py 'scripts/llm_benchmark/reports/bench-*.json' \
    --out-dir scripts/llm_benchmark/reports
```

### Re-test candidate 4 (OpenAI) when a key is available

The adapter is already wired (`LlmConfig` + `OpenAiAnswerAdapter`, `spring-ai-starter-model-openai`)
— **no code change needed**. Export a key and run the same script; the result slots straight into
the 4-row comparison table (`compare.py` already carries the `openai-gpt-4o-mini` metadata).

```bash
OPENAI_API_KEY=sk-... scripts/llm_benchmark/run_local_candidate.sh \
    openai-gpt-4o-mini openai gpt-4o-mini OPENAI_CHAT_MODEL=gpt-4o-mini
python3 scripts/llm_benchmark/compare.py 'scripts/llm_benchmark/reports/bench-*.json' \
    --out-dir scripts/llm_benchmark/reports   # now includes openai-gpt-4o-mini
```

> Measurement only. Selecting OpenAI for the **pilot** still needs `api.openai.com:443` on the
> egress allowlist (ADR-0039) + the OQ-009 US-chat-egress sign-off, independent of TTFT.

### Manual (without the wrapper)

```bash
# start the backend with the candidate env, redirecting stdout to a log, then:
python3 scripts/llm_benchmark/run_benchmark.py --base-url http://localhost:8080 \
    --label mistral-small --model mistral-small-latest --reps 3 \
    --telemetry-log /tmp/backend.log --out-dir scripts/llm_benchmark/reports
```

Outputs (git-ignored working area under `reports/`; publish the final comparison under `docs/qa/`):

- `bench-<label>.json` / `.md` — per-candidate raw turns + aggregate.
- `comparison-<date>.json` / `.md` — the ADR-0045 decision table across candidates.

## After the runs

1. Publish `comparison-<date>.{json,md}` to `docs/qa/` as the versioned TASK-BE-033 evidence.
2. Update **ADR-0045** with the chosen provider/model (or "keep Mistral small") and move it
   Proposed → Accepted, citing the comparison table.
3. The default provider swap (if any) is a separate change (config/adapter behind the port).

## Gotchas (found during the 2026-08-27 EU/on-prem runs)

- **Keyless OpenAI boot:** the `spring-ai-starter-model-openai` starter also auto-configures
  audio-speech / audio-transcription / image models that eagerly require `spring.ai.openai.api-key`,
  so the backend **crashes on startup on every non-OpenAI run** unless the *full* OpenAI auto-config
  set is excluded. This is already fixed in `VoiceSupportApplication` (all six OpenAI auto-configs
  excluded; the chat bean is gated on `provider=openai`). Don't re-add only chat/embedding/moderation.
- **Single-Ollama contention:** with `LLM_PROVIDER=ollama`, chat (`llama3.1:8b`) and the mandatory
  embeddings (`nomic-embed-text`) hit the **same** Ollama, so each turn thrashes a model swap and the
  embedding call trips the 5 s default → `ERR_INTERNAL` (`Read timed out`) on ~every turn. Raise
  `EMBEDDING_TIMEOUT_MS`/`RETRIEVAL_TIMEOUT_MS` (e.g. 30 s/35 s). The swap latency then lands in
  `backend_first_token`, so that number **overstates** a dedicated-capacity deployment — report the
  raw `llm_first_token` alongside it, and re-measure on separate chat/embedding capacity for a verdict.
- **`mistral-large` throttling:** the large model is rate-limited on the dev API tier (many
  `ERR_UPSTREAM`) and needs raised LLM budgets; even then the p50/p95 are over the *successful*
  turns only — note the error count next to the latency.
- **JDK on PATH:** Maven may use a JDK that `java` on the shell PATH can't find. The wrapper resolves
  it (`$JAVA_HOME` → `/usr/libexec/java_home` → `mvn -v` runtime); if running the jar by hand, set
  `JAVA_HOME` explicitly.

## Notes

- `openai-gpt-4o-mini` requires the OpenAI adapter (see `LlmConfig` + `OpenAiAnswerAdapter`) and
  a `spring-ai-starter-model-openai` dependency; US chat egress is a compliance decision (OQ-009),
  not only latency — it may be rejected on residency grounds regardless of TTFT.
- A cascade chat swap **cannot** reach the ~800 ms aspirational bar (that is a speech-to-speech
  property, ADR-0029); the realistic goal is shaving the backend-first-token tail toward the
  1.5 s mouth-to-ear ceiling, combined with WEB-035/036.
- Stdlib-only Python (`urllib`); no extra dependencies. Reuses the `run_eval.py` report style.
