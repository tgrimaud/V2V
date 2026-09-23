# TASK-BE-033 — LLM provider/model benchmark evidence (ADR-0045)

**Status:** 🔧 In progress — EU/on-prem subset measured (2026-08-27); OpenAI (candidate 4) deferred (no API key, OQ-009).
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

## Results (2026-08-27, local EU/on-prem subset)

Source: `scripts/llm_benchmark/reports/comparison-2026-08-27.md` (per-candidate
`bench-<label>.json` regenerable via `scripts/llm_benchmark/run_benchmark.py`). Server slices
from backend `[TELEMETRY]`; 5 FR billing questions × 3 reps (+1 discarded warm-up) = 15 scored
turns per candidate. Latency cells are **p50 / p95 (ms)**.

| Candidate | model | llm_first_token | backend_first_token | Δbft p95 vs baseline | grounded | conf | €-flags | err |
|---|---|---|---|---:|---:|---:|---:|---:|
| `mistral-small` | `mistral-small-latest` | 401 / 2472 | **844 / 3039** | baseline | 1.0 | 0.756 | 0 | 0 |
| `mistral-large` | `mistral-large-latest` | 7972 / 22108 | 8789 / 24108 | +21069 | 0.833 | 0.765 | 4 | 9 |
| `ollama-llama31-8b` | `llama3.1:8b` | 338 / 5028 | 2505 / 8823 | +5784 | 1.0 | 0.756 | 0 | 0 |
| `openai-gpt-4o-mini` | `gpt-4o-mini` | — | — | — | — | — | — | — |

## Run conditions & caveats (read before quoting numbers)

- **Environment:** local dev — one laptop Postgres/pgvector (KB 10 163 chunks incl. 1 213 billing)
  + one **shared** Ollama serving *both* embeddings (`nomic-embed-text`) and, for candidate 3,
  chat (`llama3.1:8b`). Not the pilot topology; absolute ms are indicative, **not** an SLO claim.
- **`mistral-large` is disqualified for the latency gate,** on three independent grounds: (1) an
  order-of-magnitude slower first token (backend p50 8.8 s / p95 24 s); (2) **9/15 turns errored**
  (`ERR_UPSTREAM`, API-tier throttling of the large model even at 30 s budgets) — the p50/p95 above
  are over the **6 successful** turns only and understate the real cost; (3) it dropped one grounded
  answer (0.833) and raised **4 amount-mention flags** (heuristic; more prone to volunteering figures)
  at **20× the price** ($2/$6 vs $0.10/$0.30). No latency reason to prefer it.
- **`ollama-llama31-8b`'s `backend_first_token` is contention-polluted, not a pure-chat verdict.**
  Its raw **chat** first token (`llm_first_token` p50 **338 ms**) actually *beats* Mistral-small's
  401 ms, but the *preceding* embedding hop fought the chat model for the single Ollama instance:
  every turn thrashed `llama3.1:8b ↔ nomic-embed-text` model swaps, so the first Ollama run failed
  **15/15** on embedding `Read timed out` at the default 5 s budget. It only completed after raising
  `EMBEDDING_TIMEOUT_MS`/`RETRIEVAL_TIMEOUT_MS` to 30 s/35 s — and that swap latency lands in
  `backend_first_token` (2505/8823), **not** in the model itself. A fair on-prem verdict needs a
  box with **dedicated chat + embedding capacity** (separate instances or a GPU that keeps both
  models resident), tracked as a follow-up.

## Decision (recommendation — pending user/ADR sign-off)

- **Keep `mistral-small-latest` for the pilot.** Among the measured EU/on-prem options it is the
  only one that meets the gate direction (`backend_first_token` p95 ~3.0 s here, consistent with the
  ~1.4 s live-WS p95), with **perfect grounding, zero errors, zero amount flags**, the lowest cost,
  and an **already-allowlisted** EU egress. `mistral-large` is rejected (above). `ollama` is
  **promising** (fastest raw chat token, zero egress) but **unproven** until re-measured on
  dedicated capacity — it is the recommended sovereignty fallback to validate next, not a pilot swap.
- **OpenAI (`gpt-4o-mini`) not measured here** (no API key; US egress is an OQ-009 call). The
  adapter is wired so it can be added to this table **without any code change** once a key exists —
  re-test with one command and re-merge:

  ```bash
  OPENAI_API_KEY=sk-... scripts/llm_benchmark/run_local_candidate.sh \
      openai-gpt-4o-mini openai gpt-4o-mini OPENAI_CHAT_MODEL=gpt-4o-mini
  python3 scripts/llm_benchmark/compare.py 'scripts/llm_benchmark/reports/bench-*.json' \
      --out-dir scripts/llm_benchmark/reports   # 4-row table incl. openai-gpt-4o-mini
  ```

  ADR-0045 is deliberately kept **Proposed** (not force-Accepted) so this re-test can complete the
  table before the final EU-vs-US decision. Measurement ≠ pilot authorization (OQ-009 still gates use).
- **Net:** this closes ADR-0045's Direction-A latency question for the EU/on-prem candidates —
  the chat-model swap is **not** the lever that fixes the ADR-0029 gate (Mistral-small is already
  near-optimal for a cascade); the dominant remaining slice stays the **STT finalize tail**
  (TASK-STT-014). Move ADR-0045 Proposed → Accepted as "keep Mistral small; Ollama = sovereignty
  fallback to re-measure on dedicated capacity; OpenAI gated on OQ-009" once the user confirms.

## Notes

- A cascade chat swap **cannot** reach the ~800 ms aspirational bar (speech-to-speech property,
  ADR-0029); the realistic goal is shaving the backend-first-token tail toward the 1.5 s
  mouth-to-ear ceiling, combined with WEB-035/036.
- OpenAI introduces **US chat egress** — a compliance decision (OQ-009), not only latency; it may
  be rejected on residency grounds regardless of TTFT.
- Reused evidence: `docs/qa/task-web-036-topk-ab-report.json`, `docs/qa/task-web-035-finalize-budget-report.json`,
  `docs/qa/task-web-039-ws-live-latency-evidence.md`.
