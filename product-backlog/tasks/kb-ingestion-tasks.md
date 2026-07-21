# Knowledge Base Ingestion — Technical Tasks

Follow-up ingestion connectors built on the **KB ingestion socle** delivered in
`TASK-BE-003` (pivot `SourceDocument`, `KnowledgeSourceConnector` port, idempotent
`KnowledgeSyncService` with the `kb_source_state` ledger, pgvector + Ollama
embeddings). New sources plug in as additional `KnowledgeSourceConnector` beans and
are picked up automatically by the sync service — no core change.

These form the **Sprint 8** theme (CSV KB ingestion), scheduled after the Sprint 7
answer-engine core, per product decision (2026-07-18, sprint set 2026-07-21).

> Note: this connector was drafted as `TASK-BE-011`, but that ID was used and
> delivered in Sprint 7 for the backend latency levers. It is renumbered to
> **TASK-BE-013** here; the batch embedding/insert work is split out as
> **TASK-BE-014**.

| Task | Title | Classification | Depends on | Status |
|---|---|---|---|---|
| TASK-BE-013 | `CsvArticleConnector` + embedding `DomainClassifier` — bulk KB ingestion from `articles.csv` | V1 core (KB content) | TASK-BE-003 | Planned (Sprint 8) |
| TASK-BE-014 | Batch embedding/insert (`VectorStorePort.storeChunks`) + sync progress metrics/logs | V1 core (KB content) | TASK-BE-013 | Planned (Sprint 8) |

---

## TASK-BE-013 — CsvArticleConnector + Embedding DomainClassifier (bulk KB ingestion)

**Parent:** EPIC-005 (Answer engine / knowledge base)
**Related enabler:** TASK-BE-003 (ingestion socle + Markdown connector)
**Related decision:** ADR-0030 (to create — KB connector deps + HTML-to-text +
`DomainClassifier`)
**Classification:** V1 core — provides the real operator KB content the answer
engine retrieves from.
**Status:** Planned (Sprint 8)
**Priority:** High
**Branch:** `task/TASK-BE-013-csv-article-connector`

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
- **CSV parsing** via **Apache Commons CSV** (RFC-4180): the HTML `content` has
  embedded newlines and escaped quotes (`""`), so a hand-rolled split is unsafe.
  Stream rows (do not load the whole file into memory).
- **HTML → plain text** via **jsoup** before the pivot, so chunks and embeddings are
  clean text (strip tags, decode entities, drop `<img>`/scripts, keep link text).
- **Domain classification** (`articles.csv` is mixed — no domain column): a
  `DomainClassifier` port populates `domain` before `SourceDocument.create(...)`.
  Retained implementation: **`EmbeddingDomainClassifier`** — embed the article text
  (Ollama `nomic-embed-text`, 768) and pick the closest domain anchor
  (`billing`/`support`/`commercial`) above a configurable threshold, else `general`.
  A `DefaultGeneral` impl preserves the current behaviour. Port pure in the domain,
  embedding access in an infra adapter; anchors + threshold configurable; testable
  with a fake `EmbeddingModel` (no network). Reused later by EPIC-011 for query-time
  intent classification.
- **Language**: `en` default for this connector (config `csv-default-language`) — the
  Eir corpus is English (product default language), unlike the French Markdown dev
  FAQ, which coexists.
- **Batch embedding/insert + sync observability**: split out to **TASK-BE-014**.

### Acceptance

- A sync run ingests all CSV articles; a second run is a no-op (idempotent via
  `content_hash`); editing/removing rows re-ingests/purges via the ledger.
- Stored chunk content is plain text (no HTML tags); every chunk carries a
  **classified** `domain` (via `DomainClassifier`, fallback `general`) and
  `source_type = "csv-article"`.
- `DomainClassifier` is exercised: articles clearly in a domain get that domain,
  ambiguous ones fall back to `general`; classification is deterministic and
  covered by unit tests with a fake `EmbeddingModel`.
- Bulk ingest uses the batched embedding/insert delivered in **TASK-BE-014**; total
  ingest time and throughput are reported (latency evidence).
- `mvn test` stays infra-free (domain fakes for the connector, sync and classifier);
  a small live/IT run validates the real corpus against Postgres + Ollama.

### Open questions

- **Domain taxonomy source**: can the real Eir export provide a category/section per
  article (or a `document_id → domain` sidecar)? If yes, a source-provided classifier
  beats the heuristic; otherwise keep `EmbeddingDomainClassifier`. (To record as an
  OQ.)
- **Answer language** (English default for Eir) + FR(dev)/EN(prod) mix in the same
  vector store (retrieval pollution risk; possible future `language` filter) —
  tracked as **TASK-BE-015** (scope TBD: this sprint or later).
- Whether the corpus is a one-off load or a periodically-refreshed source (affects
  scheduling and the ledger diff semantics).
- Licensing/PII review of the third-party operator content before pilot.

---

## TASK-BE-014 — Batch Embedding/Insert + Sync Observability

**Parent:** EPIC-005 (Answer engine / knowledge base)
**Related enabler:** TASK-BE-003 (ingestion socle), TASK-BE-013 (CSV connector)
**Classification:** V1 core — makes bulk CSV ingestion viable (performance).
**Status:** Planned (Sprint 8)
**Priority:** High
**Branch:** `task/TASK-BE-014-batch-embedding`

### Context

`PgVectorStoreAdapter` currently stores one chunk per `vectorStore.add(List.of(one))`
call (~40 ms/chunk on CPU Ollama observed in BE-003). For thousands of CSV articles
this is too slow and can time out the `POST /api/knowledge/sync` request.

### Objective

Store chunks in batches so a full-corpus sync completes within a documented bound,
and expose ingestion progress/throughput for monitoring.

### Scope

- Extend `VectorStorePort` with a batched `storeChunks(...)` (group `add` → batch
  embedding) and use it from `KnowledgeSyncService.reingest`. Update **all**
  implementers, including test fakes (e.g. `FakeVectorStorePort`).
- `[KB-SYNC]` structured logs + metrics: docs processed, chunks, per-batch timing,
  total duration and chunk throughput; report a documented ingest-time bound.
- Keep idempotency and deletion-diff semantics unchanged.

### Acceptance

- A full `articles.csv` sync completes within the documented bound and reports
  throughput; a second run is a no-op (idempotent).
- `VectorStorePort` change is reflected in every implementer + fake; `mvn test`
  stays infra-free; a live/IT run validates real bulk ingest against Postgres +
  Ollama.

### Open questions

- Optimal batch size vs Ollama embedding throughput and Postgres insert size.
- Whether to make sync asynchronous (job + status) if the bound is still too long
  for a single HTTP request.
