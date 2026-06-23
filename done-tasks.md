# Done tasks

## 2026-06-23 — Socle KB multi-sources (Lot 0) + docs

**Summary:**

- Ajout d'un **socle d'ingestion KB source-agnostique** (hexagonal) : format pivot `SourceDocument`, ports `SyncKnowledgeSourceUseCase` / `KnowledgeSourceConnector` / `KnowledgeSourceStatePort`, `VectorStorePort` étendu (`storeChunk` enrichi + `deleteBySource`).
- `KnowledgeSyncService` : synchro **idempotente** (skip par `content_hash`, upsert, deletion-diff). `TextChunker` extrait de `KnowledgeIngestionService` (DRY).
- Adapters : `PgVectorStoreAdapter` (métadonnées JSONB enrichies + delete par source via `Filter.Expression`), ledger JPA `kb_source_state`, `MarkdownFolderConnector` de référence (front-matter YAML via SnakeYAML).
- `KnowledgeSyncScheduler` (pull planifié cron, configurable/désactivable) + endpoints `POST /api/knowledge/sync[/{sourceType}]`. Upload ponctuel `/ingest` conservé.
- Migration de la "fake" KB : front-matter `domain` ajouté aux 3 markdown (support/billing/commercial) — comportement identique à l'ancien seeding.
- **Décision** : on reste sur **Ollama** pour les embeddings (Mistral pour le chat). Aucune migration de dimension.
- Tests : 96 verts (12 nouveaux — `TextChunker`, `KnowledgeSyncService`, `MarkdownFolderConnector`).
- Docs : `architecture.md` (section multi-sources + clarif LLM/embeddings + ADR-011), `README.md`, et diagramme `docs/architecture-kb.drawio`.

### Files changed
- `backend/.../domain/model/{SourceDocument,ContentHash,SyncReport}.java` — modèle pivot + hash + rapport.
- `backend/.../domain/service/{KnowledgeSyncService,TextChunker}.java` — synchro + chunker partagé.
- `backend/.../domain/port/in/SyncKnowledgeSourceUseCase.java`, `port/out/{KnowledgeSourceConnector,KnowledgeSourceStatePort}.java`, `port/out/VectorStorePort.java` — ports.
- `backend/.../infrastructure/adapter/out/source/MarkdownFolderConnector.java`, `adapter/out/persistence/{KbSourceStateEntity,KbSourceStateId,KbSourceStateRepository,JpaKnowledgeSourceStateAdapter}.java`, `adapter/out/vectorstore/PgVectorStoreAdapter.java` — adapters.
- `backend/.../infrastructure/scheduler/KnowledgeSyncScheduler.java`, `config/SchedulingConfig.java`, `config/DomainServiceConfig.java` — scheduler + câblage.
- `backend/.../adapter/in/rest/KnowledgeController.java` — endpoints sync.
- `backend/src/main/resources/application.yml` — clés `markdown-path`, `default-language`, `sync-cron`.
- `knowledge-base/{telecom,billing,commercial}-faq.md` — front-matter `domain`.
- `docs/{architecture.md,development-guide.md}`, `README.md`, `docs/architecture-kb.drawio` — documentation.
