# Sprint 8 — CSV Knowledge-Base Ingestion (articles.csv)

## Sprint Objective

Ingest the real operator knowledge base delivered as a CSV export (`articles.csv`,
columns `document_id,title,content` where `content` is rich HTML) into the vector
store, through a new `CsvArticleConnector` that plugs into the existing KB ingestion
socle (`KnowledgeSourceConnector` port → idempotent `KnowledgeSyncService` → ledger
`kb_source_state` → pgvector + Ollama embeddings, delivered in TASK-BE-003). The CSV
has no domain column (everything is mixed), so ingestion also classifies each article
into a business domain via an embedding-based `DomainClassifier`, making the content
routable by the future orchestrator (EPIC-011).

This is a **content + ingestion** sprint. It is **not** an identity/BSS/PDF/comparison
sprint (that is the tentative Sprint 9, EPIC-002/003/004) and **not** an orchestration
sprint (EPIC-011, after this one). It reuses the Sprint 7 answer engine unchanged.

## Status

**Status:** Planned (opened 2026-07-21). Theme set by user decision: the billing /
identity theme is shifted to Sprint 9, telephony/Genesys to Sprint 10.

## Roadmap Context

| Sprint | Theme | State |
|---|---|---|
| Sprint 6 | Streaming voice loop + latency | ✅ Done (2026-07-17) |
| Sprint 7 | Real answer engine — RAG over the KB (EPIC-005) | ✅ Done (2026-07-20) |
| **Sprint 8** | **CSV KB ingestion — `CsvArticleConnector` + embedding `DomainClassifier` (EPIC-005) — this sprint** | Planned |
| Sprint 9 (tentative) | Customer identity + BSS/PDF evidence + deterministic comparison (EPIC-002/003/004) | Planned — gated by OQ-001/003/004 |
| Sprint 10 (tentative) | Telephony channel (US-018) + Genesys advisor handoff (EPIC-007) | Planned — gated by OQ-006 |

## Why now (state that justifies the sprint)

- Sprint 7 proved the KB-grounded answer engine on a small French Markdown FAQ. The
  real target operator content (Eir, Irish — **English becomes the product default
  language**) is delivered as a CSV export, not Markdown.
- The socle was designed for exactly this (new sources plug in as connector beans,
  auto-collected by `KnowledgeSyncService`); this sprint exercises that extension
  point at scale (~thousands of HTML articles) for the first time.
- Domain tagging at ingestion is the prerequisite that makes the future orchestrator
  (EPIC-011) able to route a question to the right specialist domain.

## Tickets

| Task | Title | Classification | Depends on | Status |
|---|---|---|---|---|
| TASK-BE-013 | `CsvArticleConnector` + embedding `DomainClassifierPort` — bulk KB ingestion from `articles.csv` (CommonsCSV parse, jsoup HTML→text, `sourceId=document_id`, `language=en`, domain classified vs anchors) | V1 core (KB content) | TASK-BE-003 | In review — implemented, adversarial 92/100, QA PASS + live-validated (threshold calibrated 0.55); awaiting user validation |
| TASK-BE-014 | Batch embedding/insert — extend `VectorStorePort` with a batched `storeChunks` + sync progress metrics/logs (perf, anti-timeout for thousands of articles) | V1 core (KB content) | TASK-BE-013 | In review — implemented + live-validated (75s→44.7s, 42.7 chunks/s), 178 tests green; awaiting adversarial review + QA |

Full ticket details: [../tasks/kb-ingestion-tasks.md](../tasks/kb-ingestion-tasks.md).

## Decisions and dependencies

- **ADR-0030** (to create): multi-format KB connector, dependency choice
  `jsoup` (HTML→text) + `Apache Commons CSV` (RFC-4180 parser — the HTML `content`
  has embedded newlines and escaped quotes, a hand-rolled parser is not safe),
  HTML-to-text policy, `document_id` as stable `sourceId`, `language=en` default for
  this connector, and the `DomainClassifier` port (default `general` +
  `EmbeddingDomainClassifier`).
- **DomainClassifier** (embedding): embed the article text (Ollama `nomic-embed-text`,
  768) and pick the closest domain anchor (`billing`/`support`/`commercial`) above a
  configurable threshold, else `general`. Reused later by EPIC-011 for query-time
  intent classification.

## Out of scope / follow-ups

- **TASK-BE-015 — answer language handling** (bot answers in the question/content
  language, English default): tracked as a follow-up; decision pending (include here
  or later). See OQ on FR(dev)/EN(prod) mix in the same vector store.
- **EPIC-011 — orchestration / domain routing**: consumes these domain tags at query
  time; separate sprint after this one.
- Generic PDF/Confluence/DB connectors (post-MVP roadmap).

## Exit criteria

- A sync run ingests all CSV articles; a second run is a no-op (idempotent via
  `content_hash`); edited/removed rows re-ingest/purge via the ledger.
- Stored chunk content is plain text (no HTML); every chunk carries a classified
  `domain` and `source_type = "csv-article"`.
- Bulk ingest uses batched embedding/insert; total ingest time + throughput reported.
- `mvn test` stays infra-free (domain fakes for connector, sync and classifier); a
  small live/IT run validates the real corpus against Postgres + Ollama.
- Adversarial review ≥ 90 % + QA per ticket; docs (`docs/knowledge-base/…`,
  `application.yml` keys) updated with the code.
