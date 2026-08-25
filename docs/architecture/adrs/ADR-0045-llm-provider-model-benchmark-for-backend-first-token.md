# ADR-0045: LLM Provider/Model Benchmark For Backend First-Token (Cascade Chat, Lever B)

## Status

Proposed (2026-08-25). Framing + decision criteria recorded; the **decision is
deferred** until the benchmark spike **TASK-BE-033** produces the data. Scopes
**Direction A** of ADR-0029 ("OpenAI as the cascade chat LLM") — not Direction B
(Realtime speech-to-speech, which stays out of scope per ADR-0012/ADR-0029).

## Context

The ADR-0029 pilot latency gate (mouth-to-ear p95 ≤ 1.5 s / `time_to_first_audio`
p95 ≤ 1.2 s) is still **FAILED**. The two follow-up levers off the reference
measurement (TASK-WEB-032) narrowed the cause to two post-end-of-turn slices, and one
is now essentially closed:

- **TASK-WEB-036 (retrieval top-k 8→5):** sub-spanning `backend.first_token` via the
  existing per-slice telemetry showed **LLM first-token is ~87 %** of the backend slice
  (retrieval only ~294 ms p95). top-k 8→5 halved the backend tail (p95 2647 → 1414 ms
  isolated), grounding preserved. The residual is **model-inherent** — the LLM's
  time-to-first-token, not retrieval.
- **TASK-WEB-035 (STT finalize budget):** capped the STT time-to-final tail
  (p95 ~4042 → 1224 ms) with a partial-snapshot fallback.

After both, the live warm 15-call WebRTC re-score (real Gradium + Mistral,
top-k=5) lands at **mouth-to-ear p95 2777 ms** with the per-slice budget:

| Post-EOT slice p95 (ms) | value | note |
|---|---:|---|
| end_of_turn hold | 350 | false-cut floor 250 ms (TASK-WEB-015) |
| stt time-to-final | 1224 | capped by WEB-035 budget |
| **backend_first_token** | **1199** | **LLM-first-token bound — the largest remaining reducible slice** |
| tts_first_audio | 393 | Gradium streaming floor |

The backend first-token is now the **largest remaining reducible slice**, and it is
dominated by the chat LLM's TTFT. Prompt/context trimming has reached diminishing
returns (system prompt already ~600 chars, TASK-BE-011; top-k already at 5). The
remaining lever on this slice is the **model/hosting choice itself** — which ADR-0029
flagged as Direction A but never benchmarked.

Constraints that make this a structural decision (not just a config tweak):

- **Data residency / sovereignty:** Mistral (EU) vs OpenAI (US remote) vs a
  co-located model have very different data-egress and compliance profiles; the pilot
  egress allowlist (ADR-0039) currently permits `api.mistral.ai:443` only for chat.
- **Network dependency & reversibility:** a remote provider adds a cloud hop on the
  latency-critical path; a co-located model removes the hop at an infra cost.
- **Cost:** per-token pricing vs self-hosted GPU/CPU infra.
- **Provider port:** ADR-0026/DEC-011 already keep chat behind a replaceable
  `LlmPort` (`voice-support.llm.provider`: `mistral-api` default, `ollama`
  alternative), so swapping the model is an adapter/config change — but adding
  **OpenAI** as a candidate needs a (throwaway or real) adapter to measure it.

## Decision

**Run a data-driven benchmark spike (TASK-BE-033) before choosing**, rather than
committing to a provider from intuition. The spike measures each candidate on the
same billing fixture set through the existing guarded `converse-stream` path and
reports a comparison table; **this ADR moves to Accepted only once that data exists**
and a provider/model is selected.

Candidates (confirmed 2026-08-25):

1. **Mistral `mistral-small-latest` (current baseline)** — EU sovereignty, already
   wired; the reference to beat.
2. **Mistral `mistral-large-latest`** — same residency, check whether a larger model
   changes TTFT materially (usually worse TTFT, better quality).
3. **Co-located Ollama model** (e.g. a small instruct model on the backend VM) — no
   cloud hop, no chat egress; infra cost + quality trade-off.
4. **OpenAI `gpt-4o-mini`** — typically fast TTFT, but US-remote (residency) + a new
   egress allowlist entry; Direction A only (cascade chat, **not** Realtime).

Benchmark criteria (all measured, none assumed):

- **TTFT:** `llm_first_token` and `backend_first_token` p50/p95 on the billing set.
- **Answer quality / grounding:** grounded rate, confidence, correctness on the
  fixture answers (DEC-002 must hold — no fabricated amounts); no regression vs
  Mistral-small baseline.
- **Cost:** per-turn cost estimate (per-token pricing or amortized infra).
- **Data residency / sovereignty:** EU vs US vs on-prem; egress allowlist impact.
- **Reversibility:** stays behind `LlmPort`; the decision must not couple the domain
  to a provider SDK (ADR-0026).

The provider port stays agnostic regardless of outcome; the ADR records the chosen
default and its consequences.

## Consequences

**Positive**

- Turns the last reducible latency slice into a **measured** decision instead of a
  guess; directly targets the ADR-0029 gap (backend first-token ~1199 ms p95).
- Keeps the choice reversible (port-based) and forces the residency/cost trade-offs
  to be explicit before any pilot commitment.

**Negative / risks**

- **A cascade chat swap alone will not reach the ~800 ms aspirational bar** (ADR-0029:
  sub-second is a speech-to-speech property). Realistic outcome: shave the
  backend-first-token tail to approach — not guarantee — the 1.5 s mouth-to-ear
  ceiling, combined with WEB-035/036.
- **OpenAI introduces US data egress** for chat content — a compliance decision, not
  just a latency one; may be rejected on residency grounds regardless of TTFT.
- **A co-located model adds infra** (GPU/CPU, ops) and its quality on FR billing
  content is unproven — must clear the grounding/quality bar to qualify.
- Adding an OpenAI adapter for the spike is throwaway effort if OpenAI is not chosen.

**Re-decision triggers**

- A residency mandate (forces EU-only → Mistral / on-prem).
- Realtime speech-to-speech becoming viable with grounding/guardrails preserved
  (that is Direction B / a separate ADR, per ADR-0029).

## Alternatives Considered

- **Do nothing (keep Mistral small):** the honest baseline. Rejected as the *default*
  answer only because the slice is now the dominant reducible one and has never been
  benchmarked — but it remains a valid outcome if no candidate beats it on the
  combined criteria.
- **Further prompt/context trimming:** diminishing returns (WEB-036) — prompt already
  ~600 chars, top-k already 5; not a structural lever anymore.
- **OpenAI Realtime (speech-to-speech):** out of scope here (Direction B, ADR-0029);
  makes RAG grounding / DEC-002 / guardrails / memory materially harder (ADR-0012).
- **Deciding now without data:** rejected — an ADR frozen on intuition has no value;
  the benchmark is cheap relative to a wrong provider commitment.

## Related Documents

- `docs/architecture/adrs/ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md` (Direction A/B framing, the gate)
- `docs/architecture/adrs/ADR-0026-backend-runtime-and-ai-framework.md` (LLM behind replaceable ports)
- `docs/architecture/adrs/ADR-0039-embeddings-placement-and-provider-egress-tst.md` (egress allowlist)
- `docs/architecture/adrs/ADR-0012-modular-voice-pipeline-over-realtime-api.md` (cascade control rationale)
- `product-backlog/tasks/backend-hardening-tasks.md` (TASK-BE-033 — the benchmark spike)
- `product-backlog/tasks/web-voice-tasks.md` (TASK-WEB-036 Lever B, TASK-WEB-035)
- `docs/qa/task-web-035-finalize-budget-report.json`, `docs/qa/task-web-036-topk-ab-report.json`
