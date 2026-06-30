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

## 2026-06-30 — Scope V1 billing Voice2Voice + decisions architecture

**Summary:**

- Definition du scope V1 : assistant vocal de support operateur cible utilisateurs finaux, centre sur l'explication des ecarts de factures a partir du BSS.
- Clarification du parcours obligatoire Voice2Voice : activation par telephone ou chat vocal web, avec ecrit seulement comme canal complementaire.
- Decision architecture : conserver le socle POC voix/RAG/orchestrateur, mais reconstruire le coeur metier autour d'un modele billing, d'un connecteur BSS lecture seule et d'un moteur deterministe de comparaison.
- Decision integration BSS : utiliser un port metier typé et des adapters BSS, pas un MCP generique dans le chemin critique client.
- Decision extensibilite : garder le produit ouvert a d'autres domaines support operateur et rendre le coeur agnostique des solutions LLM, STT et TTS.

### Files changed
- `docs/v1-scope.md` — scope V1 complet et exigences produit/non fonctionnelles.
- `docs/backlog.md` — rappel des prerequis techniques pour la cible `first audio < 700 ms`.
- `CLAUDE.md` — decisions produit et architecture a retenir.
- `AGENTS.md` — pieges a eviter pour les futurs agents.

## 2026-06-30 — Backlog produit V1 + skill Product Business + schema cible

**Summary:**

- Creation du backlog produit local dans `product-backlog/` avec index, 9 EPICs, 27 user stories, 5 decisions et 3 open questions pour preparer une future migration Jira.
- Integration du skill local `product-business` inspire de Flo pour cadrer PRD, EPICs, US, business rules et acceptance criteria au niveau produit.
- Generation du schema Draw.io cible de la solution V1 : canaux Voice2Voice, edge voix, backend billing, BSS, RAG/KB, IA agnostique, observabilite et escalade humaine.
- Clarification de workflow : conserver les artefacts produit avec le repo `voice-support-bot` dans `product-backlog/` sauf demande explicite d'un depot externe.

### Files changed
- `product-backlog/` — backlog produit V1 local et migrable Jira.
- `.cursor/skills/product-business/` — skill Product / Business local.
- `docs/diagrams/target-v1-solution.drawio` — diagramme cible editable.
- `docs/v1-scope.md` — ajouts sur Gradium/Pipecat, escalade humaine et exigences techniques structurantes.
- `CLAUDE.md`, `AGENTS.md`, `done-tasks.md` — connaissances partagees.
