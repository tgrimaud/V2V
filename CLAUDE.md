# Repository context for Claude (and similar assistants)

**Voice Support Bot** — agent vocal V2V (voice-to-voice) RAG pour le support Telecom/FAI.

> Ce repo (`voice-support-bot`) est un **repo git séparé** (branche par défaut `main`), imbriqué dans le workspace `BMad`. Les commits du bot vont ici, pas dans le repo `BMad`.

## Application layout

| Part | Path | Stack |
|------|------|-------|
| Backend | `backend/` | Java 21, Spring Boot 3.4.3, Spring AI 1.0.0, Maven, hexagonal |
| Voice agent | `voice-agent/` | Python, bridge WebSocket + Gradium STT/TTS (+ piste Pipecat) |
| Frontend | `frontend/` | React 19, TypeScript, Vite, TailwindCSS 4 |

## Product scope V1

- V1 cible les **utilisateurs finaux** et se concentre sur l'explication des ecarts de facture operateur.
- Le bot doit rester un **assistant vocal de support operateur extensible** : billing en V1, puis technique, commercial, reclamation, retention ou selfcare plus tard.
- Le parcours **Voice2Voice est obligatoire** : activation par telephone ou chat vocal web, avec ecrit seulement comme canal complementaire.
- La source de verite billing est le **BSS en lecture seule**. Le LLM formule une explication traçable apres calcul deterministe des ecarts ; il ne doit pas deviner les montants.
- Le coeur produit doit rester agnostique des fournisseurs **LLM / STT / TTS** via ports/adapters configurables pour tester facilement plusieurs solutions.
- Le backlog produit V1 vit dans `product-backlog/` (EPICs, user stories, decisions, open questions) pour rester versionne avec le repo applicatif avant migration Jira.
- Utiliser le skill local `.cursor/skills/product-business/` pour produire ou relire PRD, EPICs, US, business rules et acceptance criteria au niveau produit.
- Le schema cible editable est `docs/diagrams/target-v1-solution.drawio`.

## Deux modèles d'IA distincts (NE PAS confondre)

- **LLM / chat** = **Mistral AI** (API cloud, `mistral-small-latest`) — rédige la réponse. Provider configurable via `voice-support.llm.provider` (`mistral-api` défaut, `ollama` alt). Construit manuellement dans `DomainServiceConfig` (les auto-configs chat sont exclues dans `VoiceSupportApplication`).
- **Embedding** = **Ollama** local (`nomic-embed-text`, **768 dim**) — vectorise chunks + requêtes. `MistralAiEmbeddingAutoConfiguration` est **exclu** → l'embedding est toujours Ollama. Décision actée : on **reste sur Ollama** pour les embeddings (local/gratuit).

## Architecture (backend)

- Hexagonal : domaine pur (aucune annotation Spring), services exposés en `@Bean` dans `infrastructure/config/DomainServiceConfig`. Ports `domain/port/in` (use cases) et `domain/port/out` (dépendances).
- Tests : JUnit 5, **fakes manuels (pas de Mockito)**. Pas de `@SpringBootTest` aujourd'hui → `mvn test` ne nécessite ni DB ni Ollama.
- Stockage : **une seule base Postgres** (image `pgvector/pgvector`, port 5433). `vector_store` (Spring AI, métadonnées **JSONB**) + `kb_source_state` (ledger JPA, `ddl-auto: update`).
- Acces BSS : privilegier un port metier typé (`BssBillingPort`) avec adapters REST/SOAP/SQL/snapshot selon le SI. Ne pas mettre un MCP generique dans le chemin critique client ; le MCP peut servir a l'exploration ou aux outils internes.

### KB multi-sources (socle Lot 0)

- Format **pivot** `SourceDocument` (sourceType, sourceId, title, url, content, domain, language, updatedAt, contentHash).
- Port `KnowledgeSourceConnector` (1 par type de source) ; référence : `MarkdownFolderConnector` (lit `knowledge-base/*.md`, `domain` via **front-matter YAML**, SnakeYAML transitif via Spring Boot).
- `KnowledgeSyncService` : synchro **idempotente** (skip si `content_hash` identique, upsert sinon, deletion-diff via ledger). `TextChunker` partagé avec l'ingestion ponctuelle.
- `KnowledgeSyncScheduler` (cron `voice-support.knowledge.sync-cron`, défaut horaire, `-` pour désactiver) + endpoints `POST /api/knowledge/sync[/{sourceType}]`. L'upload ponctuel `POST /api/knowledge/ingest` reste dispo.

## API gotchas

- Endpoints KB : `POST /api/knowledge/ingest` (upload ponctuel) et `POST /api/knowledge/sync` / `/sync/{sourceType}` (synchro connecteurs).
- Conversation streaming : `GET /api/conversation/ask-stream` (SSE) ; sync : `POST /api/conversation/ask`.
- Le `domain` (support|billing|commercial) tague chaque chunk ; la recherche filtre `domain == X OR general`. Les front-matter markdown doivent matcher les domaines historiques (telecom→support, billing→billing, commercial→commercial) pour un comportement identique.

## Testing commands

```bash
cd backend && mvn test
cd frontend && npx vitest run
cd voice-agent && python -m pytest tests/
```

## Issues historically hit (and fixes)

| Issue | Resolution |
|-------|------------|
| Croire que "passer sur Mistral" suffit pour tout — l'embedding restait sur Ollama | Chat et embedding sont **2 modèles séparés**. Le chat est déjà Mistral ; seul l'embedding est Ollama (`nomic-embed-text`). |
| Vouloir `ALTER` la table `vector_store` pour enrichir les métadonnées | Inutile : Spring AI stocke les métadonnées en **JSONB**. Seule la **dimension** du vecteur est figée à la création (768). |
| Passer l'embedding à `mistral-embed` sans rien d'autre | `mistral-embed` = **1024 dim** ≠ 768 → il faut changer `spring.ai.vectorstore.pgvector.dimensions` ET **recréer** `vector_store` (DROP) + re-synchroniser. |
| Doublons après migration vers la synchro | Les lignes seedées via l'ancien `curl /ingest` n'ont pas de `source_id` → `deleteBySource` ne les voit pas. Faire `DELETE FROM vector_store;` une fois, puis `POST /api/knowledge/sync`. |
| `vectorStore.delete(...)` par source | Utiliser `VectorStore.delete(Filter.Expression)` ; construire via `FilterExpressionBuilder.and(eq("source_type",..), eq("source_id",..)).build()`. |
| Ajouter une méthode à `VectorStorePort` casse les fakes de test | Mettre à jour tous les implémenteurs : `PgVectorStoreAdapter` ET les fakes manuels (ex. `FakeVectorStorePort` dans `KnowledgeIngestionServiceTest`). |
| Parser un front-matter YAML en Java | `org.yaml.snakeyaml.Yaml` est dispo **transitivement** via Spring Boot — pas de dépendance à ajouter. |
| Ajouter une nouvelle source KB | Implémenter un `KnowledgeSourceConnector` + le déclarer en `@Bean` ; `KnowledgeSyncService` injecte `List<KnowledgeSourceConnector>` → la nouvelle source est prise automatiquement (scheduler inclus). |
| draw.io via MCP | `open_drawio_xml` ouvre l'éditeur (navigateur) ; sauvegarder aussi le `.drawio` (XML) dans `docs/` pour le versionner. |
