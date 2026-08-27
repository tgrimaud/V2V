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

```bash
# 1. Point the backend at a candidate and (re)start it. Examples:
#    Mistral small (baseline):  LLM_PROVIDER=mistral-api MISTRAL_CHAT_MODEL=mistral-small-latest
#    Mistral large:             LLM_PROVIDER=mistral-api MISTRAL_CHAT_MODEL=mistral-large-latest
#    Co-located Ollama:         LLM_PROVIDER=ollama      OLLAMA_CHAT_MODEL=<model>
#    OpenAI gpt-4o-mini:        LLM_PROVIDER=openai      OPENAI_CHAT_MODEL=gpt-4o-mini  (needs OPENAI_API_KEY)
#    (redirect backend stdout to a log so the harness can read server slices)

# 2. Benchmark that candidate:
python3 scripts/llm_benchmark/run_benchmark.py \
    --base-url http://localhost:8080 \
    --label mistral-small --model mistral-small-latest \
    --reps 3 --telemetry-log /tmp/backend.log \
    --out-dir scripts/llm_benchmark/reports

# 3. Repeat for every candidate, then merge into the ADR-0045 comparison table:
python3 scripts/llm_benchmark/compare.py \
    'scripts/llm_benchmark/reports/bench-*.json' \
    --out-dir scripts/llm_benchmark/reports
```

Outputs (git-ignored working area under `reports/`; publish the final comparison under `docs/qa/`):

- `bench-<label>.json` / `.md` — per-candidate raw turns + aggregate.
- `comparison-<date>.json` / `.md` — the ADR-0045 decision table across candidates.

## After the runs

1. Publish `comparison-<date>.{json,md}` to `docs/qa/` as the versioned TASK-BE-033 evidence.
2. Update **ADR-0045** with the chosen provider/model (or "keep Mistral small") and move it
   Proposed → Accepted, citing the comparison table.
3. The default provider swap (if any) is a separate change (config/adapter behind the port).

## Notes

- `openai-gpt-4o-mini` requires the OpenAI adapter (see `LlmConfig` + `OpenAiAnswerAdapter`) and
  a `spring-ai-starter-model-openai` dependency; US chat egress is a compliance decision (OQ-009),
  not only latency — it may be rejected on residency grounds regardless of TTFT.
- A cascade chat swap **cannot** reach the ~800 ms aspirational bar (that is a speech-to-speech
  property, ADR-0029); the realistic goal is shaving the backend-first-token tail toward the
  1.5 s mouth-to-ear ceiling, combined with WEB-035/036.
- Stdlib-only Python (`urllib`); no extra dependencies. Reuses the `run_eval.py` report style.
