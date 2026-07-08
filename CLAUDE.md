# Repository context for Claude (and similar assistants)

**Voice Support Bot** — V2V (voice-to-voice) RAG voice agent for Telecom/ISP support.

> This repository (`voice-support-bot`) is a **separate git repository** (default branch `main`) nested in the `BMad` workspace. Bot commits belong here, not in the `BMad` repository.

## Application layout

| Part | Path | Stack |
|------|------|-------|
| Backend | `backend/` | Java 21, Spring Boot 3.4.3, Spring AI 1.0.0, Maven, hexagonal |
| Voice agent | `voice-agent/` | Python, Pipecat WebRTC/Twilio + Gradium STT/TTS (custom WebSocket bridge as legacy/fallback) |
| Frontend | `frontend/` | React 19, TypeScript, Vite, TailwindCSS 4 |

## Product scope V1

- V1 targets **end users** and focuses on explaining operator invoice discrepancies.
- The bot must remain an **extensible operator support voice assistant**: billing in V1, then technical support, sales, complaints, retention, or self-care later.
- The **Voice2Voice journey is mandatory**: activation by phone or web voice chat, with text only as a complementary channel.
- The billing source of truth is the **read-only BSS**. The LLM formulates a traceable explanation after deterministic discrepancy calculations; it must not guess amounts.
- The product core must remain agnostic to **LLM / STT / TTS** providers through configurable ports/adapters so several solutions can be benchmarked easily.
- The V1 voice target starts with **Gradium + Pipecat** (`voice-agent/agent/bot.py`): WebRTC for web and Twilio Media Streams for telephony. `bridge_server.py` remains a historical POC / fallback, not the target path.
- The V1 product backlog lives in `product-backlog/` (EPICs, user stories, decisions, open questions) so it stays versioned with the application repository before a Jira migration.
- Omnichannel adversarial review (2026-07-08): overall score **2.8/5** — a solid MVP foundation, but not yet an industrialized platform without channel/backend contracts, an escalation contract, measurable SLOs, per-step/channel observability, and tested degraded modes.
- Use the local `.cursor/skills/product-business/` skill to produce or review PRDs, EPICs, user stories, business rules, and product-level acceptance criteria.
- Use the local `.cursor/skills/adversarial-architecture-review/` skill to challenge architecture choices, NFR/SLA, modularity, external-provider replaceability, and Genesys/WhatsApp/omnichannel readiness.
- Use the local `.cursor/skills/software-architect/` skill for every structural decision and create/update the corresponding ADR in `docs/architecture/adrs/`.
- The editable target diagram is `docs/architecture/diagrams/target-v1-solution.drawio`.
- Documentation under `docs/` must be written in English.
- Use `.cursor/skills/technical-writer/SKILL.md` before creating, editing,
  translating or reviewing technical documentation.
- Use `.cursor/skills/diagram-drawer/SKILL.md` before creating, editing or
  reviewing Mermaid/Draw.io diagrams.
- Use `.cursor/skills/presentation-maker/SKILL.md` before creating or refining
  high-level technical/strategy presentations from `~/Downloads/Presentation.odp`.

## Two distinct AI models (DO NOT confuse)

- **LLM / chat** = **Mistral AI** (cloud API, `mistral-small-latest`) — writes the response. Provider configurable via `voice-support.llm.provider` (`mistral-api` default, `ollama` alternative). Built manually in `DomainServiceConfig` (chat auto-configurations are excluded in `VoiceSupportApplication`).
- **Embedding** = local **Ollama** (`nomic-embed-text`, **768 dim**) — vectorizes chunks and queries. `MistralAiEmbeddingAutoConfiguration` is **excluded** -> embeddings are always Ollama. Recorded decision: **stay on Ollama** for embeddings (local/free).

## Architecture (backend)

- Hexagonal: pure domain (no Spring annotations), services exposed as `@Bean`s in `infrastructure/config/DomainServiceConfig`. Ports are `domain/port/in` (use cases) and `domain/port/out` (dependencies).
- Tests: JUnit 5, **manual fakes (no Mockito)**. No `@SpringBootTest` today -> `mvn test` requires neither DB nor Ollama.
- Storage: **one Postgres database** (`pgvector/pgvector` image, port 5433). `vector_store` (Spring AI, **JSONB** metadata) + `kb_source_state` (JPA ledger, `ddl-auto: update`).
- BSS access: prefer a typed business port (`BssBillingPort`) with REST/SOAP/SQL/snapshot adapters depending on the information system. Do not put a generic MCP in the customer runtime critical path; MCP can be used for exploration or internal tools.

### KB multi-sources (socle Lot 0)

- **Pivot** format `SourceDocument` (sourceType, sourceId, title, url, content, domain, language, updatedAt, contentHash).
- `KnowledgeSourceConnector` port (one per source type); reference implementation: `MarkdownFolderConnector` (reads `knowledge-base/*.md`, `domain` via **YAML front-matter**, SnakeYAML is transitive via Spring Boot).
- `KnowledgeSyncService`: **idempotent** sync (skip if `content_hash` is identical, upsert otherwise, deletion-diff via ledger). `TextChunker` is shared with one-shot ingestion.
- `KnowledgeSyncScheduler` (cron `voice-support.knowledge.sync-cron`, hourly default, `-` to disable) + endpoints `POST /api/knowledge/sync[/{sourceType}]`. One-shot upload `POST /api/knowledge/ingest` remains available.

## API gotchas

- KB endpoints: `POST /api/knowledge/ingest` (one-shot upload) and `POST /api/knowledge/sync` / `/sync/{sourceType}` (connector sync).
- Conversation streaming: `GET /api/conversation/ask-stream` (SSE); sync: `POST /api/conversation/ask`.
- The `domain` (support|billing|commercial) tags each chunk; search filters `domain == X OR general`. Markdown front-matter must match the historical domains (telecom -> support, billing -> billing, commercial -> commercial) to preserve behavior.
- Galaxion Billing V1: use `billing-api`, not `billing-service` (no longer used). Invoice retrieval goes through `GET /bill-run-documents/search`, then `GET /bill-run-documents/{document_id}/download`.
- No identified Galaxion endpoint provides structured invoice lines for V1; invoice detail must come from the PDF through a deterministic `InvoicePdfExtractor` before comparison.

## Testing commands

```bash
cd backend && mvn test
cd frontend && npx vitest run
cd voice-agent && python -m pytest tests/
```

## Issues historically hit (and fixes)

| Issue | Resolution |
|-------|------------|
| Believing that "switching to Mistral" is enough for everything — embedding was still on Ollama | Chat and embedding are **2 separate models**. Chat is already Mistral; only embedding is Ollama (`nomic-embed-text`). |
| Wanting to `ALTER` the `vector_store` table to enrich metadata | Unnecessary: Spring AI stores metadata as **JSONB**. Only the vector **dimension** is fixed at creation time (768). |
| Switching embeddings to `mistral-embed` and nothing else | `mistral-embed` = **1024 dim** != 768 -> `spring.ai.vectorstore.pgvector.dimensions` must change AND `vector_store` must be **recreated** (DROP) + everything must be re-synced. |
| Duplicates after migrating to sync | Rows seeded through the old `curl /ingest` have no `source_id` -> `deleteBySource` cannot see them. Run `DELETE FROM vector_store;` once, then `POST /api/knowledge/sync`. |
| Deleting by source with `vectorStore.delete(...)` | Use `VectorStore.delete(Filter.Expression)`; build with `FilterExpressionBuilder.and(eq("source_type",..), eq("source_id",..)).build()`. |
| Adding a method to `VectorStorePort` breaks test fakes | Update all implementers: `PgVectorStoreAdapter` AND manual fakes (e.g. `FakeVectorStorePort` in `KnowledgeIngestionServiceTest`). |
| Parsing YAML front-matter in Java | `org.yaml.snakeyaml.Yaml` is available **transitively** via Spring Boot — no dependency to add. |
| Adding a new KB source | Implement a `KnowledgeSourceConnector` + declare it as a `@Bean`; `KnowledgeSyncService` injects `List<KnowledgeSourceConnector>` -> the new source is picked up automatically (scheduler included). |
| draw.io via MCP | `open_drawio_xml` opens the editor (browser); also save the `.drawio` (XML) under `docs/` so it is versioned. |
| Mermaid labels on wrong arrows | Put labels such as `retrieval` and `generation` on the edge where the real interaction happens, typically adapter -> PgVector or adapter -> external LLM, not on ambiguous internal backend handoffs. |
| Draw.io detached arrows | Use explicit `exitX/exitY` and `entryX/entryY` anchors for important labeled edges, especially inside or across swimlanes. |
| Assuming `billing-service` is the Galaxion invoice source | `billing-service` is no longer used; target only `billing-api` for Billing. |
| Using `invoices/composed` as customer invoice detail | This is not the selected V1 path. Retrieve the PDF via `bill-run-documents`, then extract structured invoice JSON before the comparison engine. |
| ODP template slides stayed visually blank despite text in `content.xml` | Do not keep patching ODP placeholders blindly. Generate a PPTX with standard PowerPoint text shapes (e.g. via `python-pptx` in a temp venv) when no LibreOffice renderer is available. |
| Presentation content overflowed template frames | For `Presentation.odp`, prefer simple large layouts, one idea per slide, and two short bullets max; do not fill every placeholder just because it exists. |
