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

**Status:** In progress (opened 2026-07-21). Core tickets **TASK-BE-013 + TASK-BE-014
validated by user and merged** into `feat/restart-from-scratch` (2026-07-21, fast-forward);
their ticket branches are deleted. **TASK-BE-015 (answer language) scoped 2026-07-21 and
pulled into this sprint** (user decisions captured); implementation not started. Sprint kept
open pending TASK-BE-015. BUG-001 tracked as an out-of-sprint follow-up. Theme set by user decision: the
billing / identity theme is shifted to Sprint 9, telephony/Genesys to Sprint 10.

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
  point at real corpus scale (306 HTML articles, ~40,900 lines) for the first time.
- Domain tagging at ingestion is the prerequisite that makes the future orchestrator
  (EPIC-011) able to route a question to the right specialist domain.

## Tickets

| Task | Title | Classification | Depends on | Status |
|---|---|---|---|---|
| TASK-BE-013 | `CsvArticleConnector` + embedding `DomainClassifierPort` — bulk KB ingestion from `articles.csv` (CommonsCSV parse, jsoup HTML→text, `sourceId=document_id`, `language=en`, domain classified vs anchors) | V1 core (KB content) | TASK-BE-003 | ✅ **Validated by user (2026-07-21)** — adversarial 92/100, QA PASS, live-validated (threshold 0.55); merge-ready |
| TASK-BE-014 | Batch embedding/insert — extend `VectorStorePort` with a batched `storeChunks` + sync progress metrics/logs (perf, batched embedding/insert) | V1 core (KB content) | TASK-BE-013 | ✅ **Validated by user (2026-07-21)** — adversarial 93/100, QA PASS, live-validated (75s→44.7s; full corpus ~73s, idempotent re-sync 306 skipped), 184 tests green; merge-ready |
| TASK-BE-015 | Answer language handling — assistant answers in the customer's question language (FR/EN), consistently across answers/fallbacks/refusal/escalation; configurable default (EN for Eir pilot); per-turn with session stickiness | V1 core (answer quality) | TASK-BE-013 | ✅ Merge-ready 2026-07-21 — backend + 210 tests green (9 BDD acceptance scenarios), ADR-0031; adversarial review closed + QA passed (`docs/qa/task-be-015-answer-language-qa-report.md`); pending user validation/merge |

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

- **EPIC-011 — orchestration / domain routing**: consumes these domain tags at query
  time; separate sprint after this one.
- Generic PDF/Confluence/DB connectors (post-MVP roadmap).

### Follow-ups (Out Of Sprint)

Findings surfaced while testing the Sprint 8 KB but **not** part of the CSV-ingestion theme —
tracked here, prioritized separately, not in this sprint's delivery scope.

| Ticket | Finding (where it surfaced) | Owning area | Priority |
|---|---|---|---|
| [BUG-001](../bugs/BUG-001-input-guardrail-blocks-legitimate-phishing-support.md) | Input guardrail refuses legitimate "phishing/scam calls" support questions (live converse test on the full corpus) — `phishing` is in the unsafe blocklist | Answer engine / guardrails (Sprint 7, ADR-0014) | P2 |

> Note: TASK-BE-015 (answer language) was initially surfaced here as a follow-up; scoped
> 2026-07-21 and **pulled into this sprint's delivery scope** (see the Tickets table above).

## Exit criteria

- A sync run ingests all CSV articles; a second run is a no-op (idempotent via
  `content_hash`); edited/removed rows re-ingest/purge via the ledger.
- Stored chunk content is plain text (no HTML); every chunk carries a classified
  `domain` and `source_type = "csv-article"`.
- Bulk ingest uses batched embedding/insert; total ingest time + throughput reported.
- The assistant answers in the customer's question language (FR/EN) — consistently across
  answers, insufficient-evidence fallback, off-topic refusal and escalation — with English as
  the configurable default for the Eir pilot; the chosen language is observable per turn
  (TASK-BE-015).
- `mvn test` stays infra-free (domain fakes for connector, sync and classifier); a
  small live/IT run validates the real corpus against Postgres + Ollama.
- Adversarial review ≥ 90 % + QA per ticket; docs (`docs/knowledge-base/…`,
  `application.yml` keys) updated with the code.
