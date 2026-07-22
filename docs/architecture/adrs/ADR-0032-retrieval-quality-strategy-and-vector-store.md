# ADR-0032: Retrieval Quality Strategy And Vector Store (pgvector vs Qdrant)

## Status

**Proposed** (stub, 2026-07-22) — raised while triaging
[BUG-003](../../../product-backlog/bugs/BUG-003-kb-chunking-brittle-retrieval-handoff.md)
and tracked as [OQ-008](../../../product-backlog/open-questions/v1-open-questions.md).
No decision yet: this ADR records the framing and the lever order so the choice is made
**after** BUG-003 is fixed and retrieval quality is re-measured on pgvector. Builds on
[ADR-0006](ADR-0006-mistral-chat-and-ollama-embeddings.md) (Ollama `nomic-embed-text`
embeddings), [ADR-0007](ADR-0007-source-document-knowledge-sync.md) (KB sync socle) and
[ADR-0030](ADR-0030-csv-knowledge-connector-and-domain-classification.md) (CSV connector,
where the chunking implicated in BUG-003 lives).

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

1. **Fix chunking** (BUG-003): correct overlap (no `X \n\n X`), keep Markdown heading with
   its body, no header-only chunks, no mid-word cuts. ~90% of the expected gain, on pgvector.
2. **topK / over-fetch + MMR (diversity)** so the answer chunk is not evicted by
   near-duplicate headers.
3. **Hybrid search** (keyword + dense), e.g. Postgres full-text `tsvector` as the sparse
   signal fused with the dense vector — directly counters "keyword-dense header outranks
   the content chunk".
4. **Cross-encoder reranker** over the over-fetched candidates, if 1–3 are insufficient.
5. **Change vector DB (→ Qdrant)** only on a concrete trigger (below).

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

- Fix BUG-003 (chunking) on pgvector, then re-measure retrieval quality (answer chunk in
  top-K, stable to phrasing, FR/EN).
- Resolve OQ-008 with that measurement; promote this ADR to Accepted (stay pgvector + hybrid)
  or Superseded/Amended (adopt Qdrant) with the concrete trigger that fired.
