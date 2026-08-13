# ADR-0032: Retrieval Quality Strategy And Vector Store (pgvector vs Qdrant)

## Status

**Proposed** (stub, 2026-07-22; framing extended 2026-08-13) — raised while triaging
[BUG-003](../../../product-backlog/bugs/BUG-003-kb-chunking-brittle-retrieval-handoff.md)
and tracked as [OQ-008](../../../product-backlog/open-questions/v1-open-questions.md).
No engine decision yet: this ADR records the framing and the lever order so the choice is
made **after** retrieval quality is re-measured on pgvector. Builds on
[ADR-0006](ADR-0006-mistral-chat-and-ollama-embeddings.md) (Ollama `nomic-embed-text`
embeddings), [ADR-0007](ADR-0007-source-document-knowledge-sync.md) (KB sync socle) and
[ADR-0030](ADR-0030-csv-knowledge-connector-and-domain-classification.md) (CSV connector,
where the chunking implicated in BUG-003 lives).

**Progress (2026-08-13):** lever 1 (chunking) is **done** — BUG-003 rewrote `TextChunker`
(contiguous single-overlap, word-boundary snap, headings attach to body, no header-only
chunks) and the corpus was re-ingested cleanly (~10 163 chunks, 0 header-only). Lever 2's
**top-K over-fetch is done** (`retrieval.top-k` 4 → 8); **MMR diversity is not yet
implemented**. BUG-004 (LLM refusal on grounded evidence) is closed separately. What is
still missing to *resolve* OQ-008 is **repeatable measurement**: the choice between
levers 2b–5 must be driven by a retrieval-quality eval, not by intuition. That eval harness
is scoped as **TASK-BE-027** (offline; needs no pilot access) and is the gate for this ADR.

## Context

V1 uses **pgvector** (a single Postgres holds `vector_store` + the `kb_source_state`
ledger; sessions elsewhere), behind `VectorStorePort` / `VectorSearchPort`. A stakeholder
suggested **Qdrant** as a possible improvement for RAG.

BUG-003 demonstrated, with live + backend-only evidence, that the current "not enough
info" failures are **not** a vector-store limitation:

- Retrieval already returns high scores (0.86) and `answerable=true`; the block is
  downstream (the LLM hands off on content-poor evidence → `OutputGuardrail` rewrites it
  to the low-confidence message).
- The evidence is content-poor because the corpus is **malformed at ingestion**:
  mid-word splits, internal `X \n\n X` duplication, header-only chunks, ~10 166 chunks for
  `articles-fr.csv`.
- Dense-only top-K with near-identical scores is **brittle**: a trivial phrasing change
  (adding "Bonjour,") reorders top-K and evicts the answer chunk. Reproduces in FR and EN.

Any vector store fed the same chunks with the same dense-only strategy would reproduce
the failure. So the real subject is the **retrieval strategy**; the engine is one lever.

## Decision (proposed framing, not yet committed)

Improve retrieval on the **current stack first**, and treat an engine change as a
last, trigger-gated lever. Proposed order (cheap → expensive):

1. **Fix chunking** (BUG-003) — ✅ **done**: correct overlap (no `X \n\n X`), keep Markdown
   heading with its body, no header-only chunks, no mid-word cuts. ~90% of the expected gain,
   on pgvector.
2. **topK / over-fetch (done, `top-k`=8) + MMR (diversity, pending — TASK-BE-028)** so the
   answer chunk is not evicted by near-duplicate headers.
3. **Hybrid search** (keyword + dense), e.g. Postgres full-text `tsvector` as the sparse
   signal fused with the dense vector — directly counters "keyword-dense header outranks
   the content chunk".
4. **Cross-encoder reranker** over the over-fetched candidates, if 1–3 are insufficient.
5. **Change vector DB (→ Qdrant)** only on a concrete trigger (below).

Each step past lever 1 is adopted **only if the measurement harness (TASK-BE-027) shows the
current levers miss the acceptance bar** — cheapest lever first, engine change last.

### Measurement protocol (the OQ-008 gate)

The decision cannot be made by intuition; it needs a repeatable, offline retrieval-quality
eval (TASK-BE-027) run against `POST /api/conversation/retrieve` on the loaded corpus:

- **Eval set:** a small, versioned, labeled set of ~20–40 real customer questions across the
  covered domains (internet/box troubleshooting, résiliation/billing) in **FR and EN**, each
  labeled with the article/section that holds the answer. Every question carries **phrasing
  variants** (bare, greeting-prefixed "Bonjour,", reworded) — the exact axis BUG-003 showed
  is brittle.
- **Metrics per configuration:** answer-chunk **recall@k** (k = 4 and 8), **MRR**, and a
  **phrasing-stability** score (does the answer chunk stay in top-K across a question's
  variants). Report per language and per domain, not just an aggregate.
- **Acceptance bar (proposed, to confirm on the baseline):** recall@8 ≥ 0.9 and
  phrasing-stability ≥ 0.9 on the eval set → **stay on pgvector, no further lever needed**.
  Below that, add the next cheapest lever (MMR → hybrid → rerank) and re-measure; only a
  fired Qdrant trigger (below) justifies the engine change.
- **Baseline first:** measure the *current* stack (fixed chunker, top-K=8, dense-only, no MMR)
  before adding anything, so each lever's marginal gain is attributable.

### Triggers that would justify Qdrant

- Native hybrid / sparse vectors (BM25/SPLADE) wanted without hand-rolling fusion in SQL.
- Volumetry ≫ V1 (well beyond ~10k chunks) or latency at scale on pgvector.
- Quantization, vector multitenancy, or advanced payload/filtered ANN needs.

## Options considered

- **A — Stay on pgvector, add hybrid + rerank (recommended for V1).** Keeps one datastore
  and the `VectorStorePort` boundary; lowest ops cost; sufficient for V1 volume. Hybrid
  fusion and rerank are extra work but store-independent.
- **B — Move to Qdrant now.** Gains native hybrid/rerank/quantization/scale, but adds a new
  service to run, a new adapter, a full re-sync, and loses the "one Postgres" simplicity —
  and does **not** fix BUG-003 by itself.
- **C — Managed vector DB (Pinecone/etc.).** Rejected for a self-hosted/portable posture and
  provider-lock-in concerns; revisit only if ops explicitly favors managed.

## Consequences

- Positive: decision is evidence-driven (measure on pgvector after BUG-003), not vendor-led;
  the port boundary keeps a future swap cheap; no premature infra.
- Negative / risk: hybrid + rerank on pgvector is non-trivial engineering; if the quality bar
  is still missed after 1–4, a later migration to Qdrant carries re-sync + adapter cost.
- Neutral: embeddings stay Ollama `nomic-embed-text` (ADR-0006) regardless of the store; a
  store change would require re-embedding only if the dimension/model changes.

## Follow-ups

- ✅ Fix BUG-003 (chunking) on pgvector (done 2026-07-22) + raise top-K to 8.
- **TASK-BE-027** — build the offline retrieval-quality eval harness + labeled eval set and
  record the **baseline** (fixed chunker, top-K=8, dense-only). This is the gate for the rest
  of this ADR; it needs no pilot/external access.
- **TASK-BE-028** — add MMR (diversity) over the over-fetched candidates, gated on the
  baseline showing eviction-by-near-duplicates persists; re-measure.
- Hybrid (`tsvector` fusion) and cross-encoder rerank stay as levers 3–4, each adopted only
  if the harness shows the previous lever misses the acceptance bar.
- Resolve OQ-008 with the harness numbers; promote this ADR to **Accepted** (stay pgvector +
  the levers that were needed) or **Superseded/Amended** (adopt Qdrant) with the concrete
  trigger that fired.
