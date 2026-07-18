# Knowledge Base Ingestion — Technical Tasks

Follow-up ingestion connectors built on the **KB ingestion socle** delivered in
`TASK-BE-003` (pivot `SourceDocument`, `KnowledgeSourceConnector` port, idempotent
`KnowledgeSyncService` with the `kb_source_state` ledger, pgvector + Ollama
embeddings). New sources plug in as additional `KnowledgeSourceConnector` beans and
are picked up automatically by the sync service — no core change.

These are **out of the Sprint 7 (answer-engine) theme** and scheduled after the
answer-engine core (BE-004…BE-006), per product decision (2026-07-18).

| Task | Title | Classification | Depends on | Status |
|---|---|---|---|---|
| TASK-BE-011 | CSV article connector — bulk KB ingestion from `articles.csv` | V1 core (KB content) | TASK-BE-003 | Planned (out of Sprint 7 theme) |

---

## TASK-BE-011 — CSV Article Connector (bulk KB ingestion)

**Parent:** EPIC-005 (Answer engine / knowledge base)
**Related enabler:** TASK-BE-003 (ingestion socle + Markdown connector)
**Classification:** V1 core — provides the real operator KB content the answer
engine retrieves from.
**Status:** Planned (out of Sprint 7 theme; schedule after the answer-engine core)
**Priority:** High
**Branch:** `task/TASK-BE-011-csv-article-connector`

### Context

The seed dataset `articles.csv` (kept out of git — external ingestion input) is an
extract of all operator support articles to load into the KB. Observed shape:

- Columns: `document_id, title, content`
- ~40,900 lines / ~3.9 MB
- **`content` is HTML** (operator support-site articles)
- **No `domain` and no `language` column**

### Objective

Ingest the CSV article corpus into the vector store through a new
`KnowledgeSourceConnector`, reusing the BE-003 idempotent sync + ledger, so RAG can
retrieve grounded operator content at scale.

### Scope

- **`CsvArticleConnector`** (`sourceType = "csv-article"`) reading the configured
  CSV path (external input; `voice-support.knowledge.csv-path`), streaming rows
  (do not load the whole file into memory). Map each row →
  `SourceDocument(sourceId = document_id, title, content, domain, language,
  updatedAt, contentHash)`.
- **HTML → plain text** in the connector before the pivot (e.g. Jsoup), so chunks
  and embeddings are clean text, not markup. New dependency to justify.
- **Domain**: no CSV column → default `general` (retrievable via the
  `domain == X OR general` filter). Optional later: classify into
  support/billing/commercial.
- **Language**: default configurable (e.g. `en` for this corpus — the sample is
  English operator content, unlike the French Markdown FAQ).
- **Batch embedding/insert**: extend `VectorStorePort` (and `PgVectorStoreAdapter`)
  to store chunks in batches instead of one `Document` per call — the current
  per-chunk `vectorStore.add(List.of(one))` is too slow for thousands of articles
  on CPU Ollama (~40 ms/chunk observed in BE-003).
- **Observability**: `[KB-SYNC]` progress + per-batch/timing logs; report total
  ingest duration and chunk throughput.

### Acceptance

- A sync run ingests all CSV articles; a second run is a no-op (idempotent via
  `content_hash`); editing/removing rows re-ingests/purges via the ledger.
- Stored chunk content is plain text (no HTML tags); every chunk carries a
  `domain` (default `general`) and the `source_type = "csv-article"`.
- Bulk ingest uses batched embedding/insert; total ingest time and throughput are
  reported (latency evidence), with a documented bound / progress logging.
- `mvn test` stays infra-free (domain fakes for the connector + sync); a small
  live/IT run validates the real corpus against Postgres + Ollama.

### Open questions

- Target `language` and whether to auto-classify `domain` for retrieval quality.
- Whether the corpus is a one-off load or a periodically-refreshed source (affects
  scheduling and the ledger diff semantics).
- Licensing/PII review of the third-party operator content before pilot.
