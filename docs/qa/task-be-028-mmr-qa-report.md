# QA Functional And Latency Report — TASK-BE-028 (MMR Diversity Re-Ranking)

## Executive Summary

- **Overall readiness:** **Go — QA Pass.** The MMR re-ranking lever ships **disabled by
  default** and, in that shipped state, retrieval is **byte-for-byte the baseline**
  (recall@8 0.90, stability 0.79, 1 eviction) with **zero MMR execution** and **zero added
  latency**. The enabled path works correctly (over-fetch ×3 → greedy MMR select-k) and, at
  the safe default `lambda=0.9`, is **quality-neutral** (recall@4 even ticks up 0.83→0.86).
- **Main blockers:** none.
- **Residual risks (non-blocking, accepted):** (1) MMR **does not fix** the single
  greeting-induced eviction (`sup-fr-slow`) — that is a recall miss (answer chunk absent from
  the over-fetched candidate set), handed to **TASK-BE-029** (query greeting-normalization),
  not a diversity problem; (2) `lambda=0.7` **degrades** retrieval (recall@8 0.90→0.86,
  stability 0.79→0.71, +1 eviction) because relevance (compressed nomic cosine ~0.49–0.80) and
  redundancy (0–1 Jaccard) are on mismatched scales — MMR must stay disabled or be re-tuned
  with min-max-normalized relevance before any enable; (3) the `[RETRIEVAL-MMR]` structured
  log is emitted at **DEBUG** (invisible at prod INFO) — the DistributionSummary metric
  `voice_support.retrieval_mmr_selected` is **not** log-gated and remains the prod signal.

## Scope Tested

- **Story:** TASK-BE-028 — over-fetch + Maximal Marginal Relevance re-ranking to reduce
  near-duplicate crowding in top-k, gated by TASK-BE-027 A/B evidence (ADR-0032 / OQ-008).
- **Channels:** `api` (`POST /api/conversation/retrieve`, pre-LLM grounding pipeline:
  input guardrail → retrieval → confidence guardrail). Channel-agnostic (domain-service lever).
- **Providers:** Ollama `nomic-embed-text` embeddings (live, 768-dim), pgvector `pg16` on
  `:5433` (**10 163 KB chunks**). No LLM involved — the `/retrieve` endpoint stops before LLM
  wording.
- **Environment:** BE-028 **freshly repackaged** jar on `:8081`, warm, MMR-adapter package at
  DEBUG so MMR execution is directly observable, correlation ids per request.
- **Eval set:** `scripts/retrieval_eval/eval_set.json` — 14 questions / 29 variants (support,
  billing, commercial; FR + EN; greeting-prefixed variants for BUG-003 stability).
- **Automation:** backend unit/component suite **347 green** (incl. 6 `MmrRerankerTest` +
  2 `KnowledgeRetrievalServiceTest` MMR cases), ArchUnit OK; harness metric tests 13 green.

## Functional Results

| Area | Status | Evidence | Notes |
|---|---|---|---|
| Shipped default = MMR **off** (source `enabled:${KB_RETRIEVAL_MMR_ENABLED:false}`) | ✅ Pass | Fresh jar, no env: **0** `[RETRIEVAL-MMR]` invocations at DEBUG over 29 variants | Confirms no MMR execution in default |
| Default retrieval quality unchanged vs baseline | ✅ Pass | Default run: recall@4 0.83, recall@8 **0.90**, MRR 0.77, stability **0.79**, block 2, evict 1 — identical to `baseline-2026-08-13` | No regression |
| Enabled path executes correctly (over-fetch ×3 → select-k) | ✅ Pass | MMR-on λ=0.9: **27** invocations, sample `fetch_k=24 candidates=24 selected=8 lambda=0.9` | 8×3=24 over-fetch verified |
| Enabled default `lambda=0.9` is quality-neutral | ✅ Pass | MMR-on λ=0.9: recall@4 **0.86** (↑), recall@8 0.90 (=), MRR 0.77 (=), stability 0.79 (=), evict 1 (=) | No harm; slight recall@4 gain |
| MMR does **not** fix the greeting eviction | ✅ Pass (expected) | `sup-fr-slow` still evicted on greeting variant with λ=0.9; answer chunk absent even from 24 over-fetched candidates | Recall miss → TASK-BE-029, documented |
| `lambda=0.7` degradation reproduced (regression guard) | ✅ Pass (expected) | A/B `reports/ab-mmr-2026-08-13.md`: recall@8 0.86, stability 0.71, evict 2 | Why MMR stays disabled |
| Best/most-relevant chunk preserved as rank-1 (confidence guardrail intact) | ✅ Pass | `MmrRerankerTest.selectsMostRelevantFirst`; live best_score unchanged in `[GROUNDING]` logs | Guardrail threshold input unaffected |
| Config toggling via env has no side effects on other slices | ✅ Pass | Guardrail block count (2) and MRR stable across arms | MMR isolated to retrieval slice |

## Latency Results

Retrieval slice only (`[TELEMETRY] slice=retrieval provider=pgvector`), warm, `:8081`,
n = 27 grounded retrieval calls per arm (guardrail-blocked variants emit no retrieval slice).

| Arm | p50 | p95 | p99 | min | max | mean | Warm/Cold |
|---|---:|---:|---:|---:|---:|---:|---|
| **MMR off (shipped default)** | 96 | 107 | 139 | 89 | 139 | 98.0 | Warm |
| **MMR on λ=0.9 (over-fetch ×3)** | 95 | 158 | 192 | 87 | 192 | 101.3 | Warm |

- **Default (off):** the code path is a plain single dense top-k search — **zero added
  latency** vs pre-BE-028. p95 107 ms is the pgvector-only cost.
- **Enabled (on):** p50 unchanged; the over-fetch ×3 + Jaccard rerank adds **~+50 ms at
  p95/p99** (bigger `LIMIT` + in-memory token-set scoring). Acceptable *if* a future quality
  win justified enabling it — currently it does not, so this cost is not paid in prod.

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| `MmrReranker` (domain) | ✅ Pass | Deterministic greedy MMR; most-relevant-first; handles k≥size, empty, λ clamp (6 unit tests) | None |
| `KnowledgeRetrievalService` | ✅ Pass | Over-fetch + rerank when enabled; delegates plain top-k when disabled (constructor overload) | None |
| `RetrievalObserverPort` + `LoggingRetrievalObserverAdapter` | ⚠️ Minor | Metric `voice_support.retrieval_mmr_selected` emitted regardless of level; structured log is DEBUG only | Consider INFO-level counter if MMR ever enabled in prod |
| `KnowledgeConfig` wiring | ✅ Pass | `enabled:false` / `lambda:0.9` / `fetch-multiplier:3` from `application.yml`; MMR-disabled bean skips reranker entirely | None |
| Eval harness (BE-027) | ✅ Pass | Reproduced baseline and A/B arms exactly; miss classification (block vs evict) stable | Reused for BE-029 |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Info (process) | Local `mvn test-compile` does **not** repackage the fat jar; a first `java -jar` used a **stale** jar (pre default-flip) and reproduced the λ=0.7 degraded numbers under "default". Fixed by `mvn -o package` before validation. | Local QA only — CI builds from source (source default is `false`). No product impact. | QA/Dev |
| Low | MMR relevance/redundancy scale mismatch (compressed cosine vs 0–1 Jaccard) makes λ non-portable across corpora. | Blocks safe enable; accepted as documented residual. | TASK-BE-028 follow-up (if revisited) |
| Low | `[RETRIEVAL-MMR]` log at DEBUG only. | Reduced log visibility if enabled; metric still emitted. | Adapter tweak if enabled |

## Open Questions

- **Product:** none new — greeting-robust recall need already captured as TASK-BE-029.
- **Architecture:** if MMR is ever enabled, min-max-normalize relevance within the candidate
  set so λ has consistent meaning (ADR-0032 follow-up).
- **Technical:** none blocking.

## Recommendation

- **Go / No-go:** **Go — QA Pass.** MMR ships **disabled by default**, proven to preserve the
  baseline exactly with zero execution and zero latency, and the enabled path is correct and
  neutral at λ=0.9. The adversarial review residuals (scale mismatch, DEBUG log) are
  **non-blocking** and documented.
- **Required fixes before pilot:** none for BE-028. The retrieval quality lever that actually
  moves the needle on the one remaining eviction is **TASK-BE-029 (query greeting-normalization)**.

## Reproduction

```bash
# Build fresh (test-compile does NOT repackage the fat jar)
cd backend && mvn -o package -DskipTests

# Arm A — shipped default (MMR off): expect recall@8=0.90 stability=0.79, 0 MMR invocations
java -jar target/voice-support-backend-0.1.0-SNAPSHOT.jar --server.port=8081 \
  --logging.level.com.voicesupport.knowledge.infrastructure.adapter.out.observability=DEBUG
python3 scripts/retrieval_eval/run_eval.py --base-url http://localhost:8081 --top-k 8 \
  --label qa-default-2026-08-13

# Arm B — MMR on lambda=0.9: expect recall@8=0.90 (neutral), 27 MMR invocations
KB_RETRIEVAL_MMR_ENABLED=true KB_RETRIEVAL_MMR_LAMBDA=0.9 KB_RETRIEVAL_MMR_FETCH_MULTIPLIER=3 \
  java -jar target/voice-support-backend-0.1.0-SNAPSHOT.jar --server.port=8081 \
  --logging.level.com.voicesupport.knowledge.infrastructure.adapter.out.observability=DEBUG
python3 scripts/retrieval_eval/run_eval.py --base-url http://localhost:8081 --top-k 8 \
  --label qa-mmron-l09-2026-08-13
```

Artifacts: `scripts/retrieval_eval/reports/baseline-qa-default-2026-08-13.{json,md}`,
`baseline-qa-mmron-l09-2026-08-13.{json,md}`, A/B `reports/ab-mmr-2026-08-13.md`.
