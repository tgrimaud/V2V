# TASK-BE-033 — LLM provider/model benchmark evidence (ADR-0045)

**Status:** 🔧 In progress — harness landed, candidate runs pending.
**Ticket:** `product-backlog/tasks/backend-hardening-tasks.md` → TASK-BE-033
**Decision:** ADR-0045 (Proposed → Accepted once this evidence exists).
**Scope:** ADR-0029 **Direction A** (cascade chat LLM first-token), not Direction B (Realtime S2S).

## Why this spike

After TASK-WEB-035 (STT finalize tail capped) and TASK-WEB-036 (top-k 8→5, which isolated
LLM time-to-first-token as ~87 % of `backend_first_token`, retrieval only ~294 ms p95), the
**backend first-token** slice is the largest remaining **reducible** post-end-of-turn slice of
the ADR-0029 gate and is **model-inherent**. Prompt/context trimming is exhausted (system prompt
~600 chars, top-k already 5). The remaining lever is the **chat model / hosting choice**.

Live WS re-measure (TASK-WEB-039, v0.7.0 through HAProxy) confirms the gate is still FAIL:
mouth-to-ear p95 **2763 ms** (≤1500), with `backend_first_token` p95 ≈ **1388 ms** as the second
largest reducible slice behind the STT tail.

## Method

- **Harness:** `scripts/llm_benchmark/run_benchmark.py` (per candidate) + `compare.py` (merge).
- **Path:** guarded `POST /api/conversation/converse-stream` — real retrieval + guardrails,
  text-in (no STT/TTS noise), `domain=null` cross-domain retrieval by design (BUG-007).
- **Fixture set:** `scripts/llm_benchmark/billing_fixtures.json` — the 5 FR billing questions
  reused from the TASK-WEB-036 top-k A/B so numbers stay comparable.
- **Per turn:** server `llm_first_token` + `backend_first_token` p50/p95 (from `[TELEMETRY]`),
  client time-to-first-chunk (proxy), grounded rate, mean confidence, DEC-002 amount-mention
  flags (manual adjudication).
- **Protocol:** warm + isolated; the backend selects the provider/model at startup
  (`LLM_PROVIDER` + model env vars), so one candidate is run, the backend is restarted, next
  candidate is run, then all per-candidate JSONs are merged into `comparison-<date>.{json,md}`.

## Candidates (ADR-0045)

| Label | Model | Wired? | Residency | Egress |
|---|---|---|---|---|
| `mistral-small` | `mistral-small-latest` | ✅ baseline | EU | `api.mistral.ai:443` (allowlisted) |
| `mistral-large` | `mistral-large-latest` | ✅ config/env | EU | `api.mistral.ai:443` (allowlisted) |
| `ollama` | co-located instruct model | ✅ config/env | on-prem | none |
| `openai-gpt-4o-mini` | `gpt-4o-mini` | ✅ adapter + dep landed (`LLM_PROVIDER=openai` + `OPENAI_API_KEY`) | US | `api.openai.com:443` (NEW, OQ-009) |

> **OQ-009 gate:** the OpenAI adapter makes the candidate _measurable_ for the spike (local run
> with an `OPENAI_API_KEY`); it does **not** authorize pilot use. Selecting OpenAI would require the
> pilot egress allowlist to add `api.openai.com:443` (ADR-0039) and a US-chat-egress compliance sign-off.

## Results

_Pending — populate from `scripts/llm_benchmark/reports/comparison-<date>.md` after the runs.
Publish the final comparison JSON + MD here as the versioned evidence._

| Candidate | llm_first_token p50/p95 | backend_first_token p50/p95 | Δbft p95 vs baseline | grounded | conf | €-flags |
|---|---|---|---|---|---|---|
| `mistral-small` | — | — | baseline | — | — | — |
| `mistral-large` | — | — | — | — | — | — |
| `ollama` | — | — | — | — | — | — |
| `openai-gpt-4o-mini` | — | — | — | — | — | — |

## Decision (fill on completion)

_Chosen provider/model (or "keep Mistral small") + rationale across latency / grounding /
cost / residency (OQ-009). Then move ADR-0045 Proposed → Accepted citing this table._

## Notes

- A cascade chat swap **cannot** reach the ~800 ms aspirational bar (speech-to-speech property,
  ADR-0029); the realistic goal is shaving the backend-first-token tail toward the 1.5 s
  mouth-to-ear ceiling, combined with WEB-035/036.
- OpenAI introduces **US chat egress** — a compliance decision (OQ-009), not only latency; it may
  be rejected on residency grounds regardless of TTFT.
- Reused evidence: `docs/qa/task-web-036-topk-ab-report.json`, `docs/qa/task-web-035-finalize-budget-report.json`,
  `docs/qa/task-web-039-ws-live-latency-evidence.md`.
