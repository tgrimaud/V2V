# Pre-LLM grounding-quality baseline report (TASK-BE-027 / ADR-0032)

> **What this measures:** success of the whole `POST /api/conversation/retrieve` pre-LLM grounding pipeline (input guardrail → retrieval → confidence guardrail), **not** isolated vector recall. A blocked guardrail decision returns no evidence, so a miss can be a guardrail block rather than a retrieval eviction — each miss is therefore classified below so the right lever is chosen (the BUG-003 lesson).

- **Date:** 2026-08-13
- **Base URL:** http://localhost:8081
- **top_k:** 8 | **domain-mode:** none
- **Eval set:** v1.0 (14 questions, 29 variants)
- **Config under test:** fixed chunker (BUG-003) + top-K over-fetch, dense-only (no MMR/hybrid/rerank)

> **Caveats:** labels (`acceptable_source_ids`) are title/section-heuristic, not adjudicated against article bodies, so treat absolute numbers as a baseline to track **deltas**, not ground truth. If pgvector uses an approximate (HNSW) index, results may vary slightly between runs.

## Acceptance check (ADR-0032 proposed bar)

- grounding recall@8 ≥ 0.9: **FAIL** (0.90)
- phrasing-stability ≥ 0.9: **FAIL** (0.79)
- Miss breakdown (top-8): guardrail-block **2**, retrieval-eviction **1** (of 29 variants)

## Aggregates

| Scope | recall@4 | recall@8 | MRR | stability | block | evict | q | v |
|---|---|---|---|---|---|---|---|---|
| overall | 0.86 | 0.90 | 0.77 | 0.79 | 2 | 1 | 14 | 29 |
| language=en | 0.67 | 0.67 | 0.46 | 0.33 | 2 | 0 | 3 | 6 |
| language=fr | 0.91 | 0.96 | 0.85 | 0.91 | 0 | 1 | 11 | 23 |
| domain=billing | 1.00 | 1.00 | 0.92 | 1.00 | 0 | 0 | 6 | 12 |
| domain=commercial | 1.00 | 1.00 | 1.00 | 1.00 | 0 | 0 | 2 | 4 |
| domain=support | 0.69 | 0.77 | 0.57 | 0.50 | 2 | 1 | 6 | 13 |

## Per-question (top-8)

| Question | lang | domain | pass@8 | best rank | flips? | flip cause |
|---|---|---|---|---|---|---|
| sup-fr-internet | fr | support | 3/3 | 1 | no | — |
| sup-fr-slow | fr | support | 1/2 | 2 | yes | retrieval |
| sup-fr-wifi | fr | support | 2/2 | 1 | no | — |
| sup-fr-tv | fr | support | 2/2 | 1 | no | — |
| sup-en-internet | en | support | 1/2 | 4 | yes | guardrail |
| sup-en-wifi | en | support | 1/2 | 1 | yes | guardrail |
| bil-fr-understand | fr | billing | 2/2 | 1 | no | — |
| bil-fr-higher | fr | billing | 2/2 | 1 | no | — |
| bil-fr-payment | fr | billing | 2/2 | 1 | no | — |
| bil-fr-consult | fr | billing | 2/2 | 1 | no | — |
| bil-fr-cancel | fr | billing | 2/2 | 1 | no | — |
| bil-en-cancel | en | billing | 2/2 | 1 | no | — |
| com-fr-subscribe | fr | commercial | 2/2 | 1 | no | — |
| com-fr-moving | fr | commercial | 2/2 | 1 | no | — |
