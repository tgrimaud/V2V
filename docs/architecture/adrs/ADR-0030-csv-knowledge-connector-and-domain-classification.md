# ADR-0030: CSV Knowledge Connector, HTML-to-Text, And Embedding Domain Classification

## Status

Accepted — extends the KB ingestion socle of
[ADR-0007](ADR-0007-source-document-knowledge-sync.md) (pivot `SourceDocument`,
`KnowledgeSourceConnector` port, idempotent sync + ledger) with a second source
connector and an ingestion-time domain classifier. Reuses the Ollama embedding
model of [ADR-0006](ADR-0006-mistral-chat-and-ollama-embeddings.md). Implemented by
TASK-BE-013 (+ TASK-BE-014 for batch insert). Feeds
[EPIC-011](../../../product-backlog/epics/v1-epics.md) (the same `DomainClassifierPort`
is reused for query-time routing).

## Context

The real target operator knowledge base (Eir, Irish — English is the product
default language) is delivered as a CSV export `articles.csv`:

- Columns `document_id, title, content`; `content` is **rich HTML**
  (`<p>`, `<h1>`, `<a>`, `<img>`, escaped quotes `""`, embedded newlines).
- ~3.9 MB, **306 articles** (~40,900 lines — HTML `content` spans many lines per article);
  kept out of git (external ingestion input).
- **No `domain` and no `language` column** — everything is mixed.

Sprint 7 proved the answer engine on a small French Markdown FAQ ingested by
`MarkdownFolderConnector`. Ingesting this CSV requires three decisions that are not
covered by the existing socle:

1. How to parse a CSV whose fields contain HTML with newlines and escaped quotes.
2. How to turn HTML into clean text for chunking/embedding.
3. How to assign a business `domain` when the source has none, so the content is
   routable (the retrieval filter is `domain == <agent> OR general`, and EPIC-011
   will route by domain at query time).

## Decision

### 1. New connector `CsvArticleConnector` (`sourceType = "csv-article"`)

Plugs into the socle as an additional `KnowledgeSourceConnector` bean (auto-collected
by `KnowledgeSyncService`; no core change). Streams rows from a configurable path
(`voice-support.knowledge.csv-path`), maps each row to a `SourceDocument` with
`sourceId = document_id` (stable → idempotency + deletion-diff), `language = en`
(config `voice-support.knowledge.csv-default-language`), `url = null`.

### 2. Dependencies (not managed by the Spring Boot BOM → explicit versions)

- **Apache Commons CSV `1.14.1`** for RFC-4180 parsing. A hand-rolled split is unsafe
  because the HTML `content` contains embedded newlines and escaped quotes.
- **jsoup `1.22.2`** for HTML → plain text. Self-contained, no runtime dependencies.

Versions are pinned in `<properties>` (`commons-csv.version`, `jsoup.version`).

### 3. HTML-to-text policy (jsoup)

Extract readable text only: strip tags, decode HTML entities, drop `<img>`, scripts
and styles, keep the visible text of links (not the URL). The cleaned text is what is
hashed (`contentHash`), chunked and embedded — never the raw markup.

### 4. Ingestion-time domain classification via a `DomainClassifierPort`

A new domain port `DomainClassifierPort.classify(title, content) -> domain` is called
by the connector before `SourceDocument.create(...)`:

- **`EmbeddingDomainClassifierAdapter`** (retained default): embed the article text
  with the existing Ollama `nomic-embed-text` model (768d) and pick the closest domain
  anchor (`billing` / `support` / `commercial`) by cosine similarity, above a
  **configurable threshold** (`voice-support.knowledge.classifier.threshold`), else
  `general`. Domain anchors (short representative texts) and the threshold are
  configuration; classification runs on the title plus a bounded prefix of the content
  (`classifier.max-chars`) to keep the embedding call cheap.

The port stays pure in the domain layer (`..domain.port.out`); the embedding access
lives in an infra adapter (`..adapter.out.classifier`). Classification is
deterministic and unit-testable with a fake `EmbeddingModel` (no network). Because the
domain is part of the ingested document, it is only re-evaluated when the
`content_hash` changes (idempotent). Connectors that do not classify (e.g.
`MarkdownFolderConnector`) keep passing their own domain, defaulting to `general`.

### 5. Bulk-ingest batching + sync observability (TASK-BE-014)

The one-chunk-per-`add` write path is too slow for hundreds of multi-chunk articles. The outbound
`VectorStorePort` exposes a batched `storeChunks(document, chunks)` (replacing the
per-chunk `storeChunk`): the `PgVectorStoreAdapter` builds all `Document`s for a
document and issues a **single** `vectorStore.add(...)`, so Spring AI performs one
embedding batch + one multi-row insert instead of one round-trip per chunk. Measured on
the 150-article Eir sample: **75 s → 44.7 s** (~40% faster), 42.7 chunks/s, distribution
unchanged (pure performance change).

Observability is a **new domain out-port `SyncObserverPort`** (`batchStored`,
`syncCompleted`) so `KnowledgeSyncService` stays pure and fake-testable; the infra
`LoggingSyncObserverAdapter` turns the events into Micrometer meters
(`voice_support.kb_sync_batch` per-document embed+insert latency p50/p95/p99,
`voice_support.kb_sync_chunks`, `voice_support.kb_sync` full-sync wall clock, all tagged
by `source_type`) plus `[KB-SYNC]` structured logs (per-batch at DEBUG, periodic
progress at INFO, a completion line carrying throughput). The real corpus is **306
articles** (the ~40,900 line count is multi-line HTML, not article count): the full corpus
ingests in **~73–92 s** in a single request, so no async job is needed at this size. An
**async job + status** stays a documented follow-up only for a hypothetical
order-of-magnitude larger corpus (embedding, not insert, is the dominant cost).

## Consequences

- The answer engine can retrieve real operator content at scale; classified domains
  make it routable by the future orchestrator (EPIC-011), which reuses the same
  `DomainClassifierPort` to classify the question at query time.
- Two new third-party dependencies enter the backend; both are self-contained,
  widely used, and pinned. Dependency governance (code-guidelines) is satisfied by
  the explicit justification above.
- The one-chunk-per-`add` insert was slow; batched `storeChunks` + the `SyncObserverPort`
  metrics/logs (section 5, TASK-BE-014) address throughput and observability. Embedding is
  now the dominant cost; the full 306-article corpus ingests in ~73–92 s (async ingest only
  needed for a far larger corpus).
- English content coexists with the French dev FAQ in one vector store. Answer
  language handling and any `language` retrieval filter are out of scope here
  (tracked as TASK-BE-015 + an open question on FR/EN mixing).

## Alternatives Considered

- **Default everything to `general`** (no classifier): functional (content stays
  retrievable) but loses domain routing precision; rejected as the target because the
  operator corpus is large and mixed. It remains the fallback whenever the classifier
  cannot decide (below threshold, blank text, or an embedding failure) and for
  connectors that pass their own domain (e.g. `MarkdownFolderConnector`).
- **Keyword/rule-based classification**: cheap and deterministic, but brittle on real
  English operator content and needs curated keyword lists; can be added later behind
  the same port.
- **LLM-based classification**: most accurate but one LLM call per article (thousands)
  at ingestion; heavier and costlier than an embedding-similarity call. Deferred; the
  port allows swapping later. Note: classification currently issues its own
  (article-level, truncated) embedding, distinct from the chunk-level storage
  embeddings — reusing the storage vectors is a possible optimization (TASK-BE-014),
  not the current behaviour.
- **Source-provided category**: best if the real Eir export exposes a category/section
  (or a `document_id → domain` sidecar) — tracked as an open question; would become a
  `DomainClassifierPort` implementation that reads the source field.
- **Hand-rolled CSV parsing / regex HTML stripping**: rejected — unsafe on HTML with
  embedded newlines, escaped quotes and entities.
