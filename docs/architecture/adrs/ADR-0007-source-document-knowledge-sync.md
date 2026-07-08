# ADR-0007: Knowledge Sync Uses A SourceDocument Pivot

## Status

Accepted

## Context

The RAG knowledge base must grow beyond manual uploads. Expected sources include
Markdown, PDF, Confluence, and possibly database-backed sources.

Each source has different metadata, update behavior, and deletion semantics.
Without a common ingestion shape, every source would leak into chunking,
embedding, vector storage, and sync logic.

## Decision

Knowledge ingestion uses `SourceDocument` as a source-agnostic pivot format.

Each connector converts its native source into `SourceDocument` values with:

- source type;
- source id;
- title;
- URL when available;
- content;
- domain;
- language;
- updated timestamp;
- content hash.

`KnowledgeSyncService` performs idempotent sync:

- skip unchanged documents by content hash;
- delete and re-ingest changed documents;
- delete documents that disappeared from the source;
- share chunking through `TextChunker`;
- store vector metadata in PostgreSQL/pgvector JSONB.

## Consequences

- New knowledge sources require a connector, not a rewrite of the ingestion
  pipeline.
- Metadata enrichment does not require schema changes in `vector_store` because
  Spring AI stores metadata as JSONB.
- The ledger table tracks source state, while vector data remains in the vector
  store.
- Legacy manually seeded chunks without source ids may need one-time cleanup.

## Alternatives Considered

- **Keep manual upload as the only ingestion path**: rejected because production
  knowledge must be synchronized and repeatable.
- **Create one ingestion pipeline per source type**: rejected because it would
  duplicate chunking, hashing, deletion, and metadata handling.

## Related Documents

- `docs/knowledge-base/knowledge-base-technical.md`
- `docs/knowledge-base/knowledge-base-guide.md`
- `docs/architecture/architecture.md`
