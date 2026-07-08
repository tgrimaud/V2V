# Repository context for Claude (and similar assistants)

**Voice Support Bot** — agent vocal V2V (voice-to-voice) RAG pour le support Telecom/FAI.

> Ce repo (`voice-support-bot`) est un **repo git séparé** (branche par défaut `main`), imbriqué dans le workspace `BMad`. Les commits du bot vont ici, pas dans le repo `BMad`.

## Application layout

| Part | Path | Stack |
|------|------|-------|
| Backend | `backend/` | Java 21, Spring Boot 3.4.3, Spring AI 1.0.0, Maven, hexagonal |
| Voice agent | `voice-agent/` | Python, Pipecat WebRTC/Twilio + Gradium STT/TTS (bridge WebSocket custom en legacy/fallback) |
| Frontend | `frontend/` | React 19, TypeScript, Vite, TailwindCSS 4 |

## Product scope V1

- V1 cible les **utilisateurs finaux** et se concentre sur l'explication des ecarts de facture operateur.
- Le bot doit rester un **assistant vocal de support operateur extensible** : billing en V1, puis technique, commercial, reclamation, retention ou selfcare plus tard.
- Le parcours **Voice2Voice est obligatoire** : activation par telephone ou chat vocal web, avec ecrit seulement comme canal complementaire.
- La source de verite billing est le **BSS en lecture seule**. Le LLM formule une explication traçable apres calcul deterministe des ecarts ; il ne doit pas deviner les montants.
- Le coeur produit doit rester agnostique des fournisseurs **LLM / STT / TTS** via ports/adapters configurables pour tester facilement plusieurs solutions.
- La cible V1 voix demarre avec **Gradium + Pipecat** (`voice-agent/agent/bot.py`) : WebRTC pour le web et Twilio Media Streams pour la telephonie. `bridge_server.py` reste un POC historique / fallback, pas le chemin cible.
- Le backlog produit V1 vit dans `product-backlog/` (EPICs, user stories, decisions, open questions) pour rester versionne avec le repo applicatif avant migration Jira.
- Revue adversariale omnicanale (2026-07-08) : score global **2.8/5** — bon socle MVP, mais pas encore plateforme industrialisee sans contrats canal/backend, contrat d'escalade, SLOs mesurables, observabilite par etape/canal et modes degrades testes.
- Utiliser le skill local `.cursor/skills/product-business/` pour produire ou relire PRD, EPICs, US, business rules et acceptance criteria au niveau produit.
- Utiliser le skill local `.cursor/skills/adversarial-architecture-review/` pour challenger les choix d'architecture, NFR/SLA, modularite, remplaçabilite des providers externes et readiness Genesys/WhatsApp/omnicanal.
- Le schema cible editable est `docs/architecture/diagrams/target-v1-solution.drawio`.
- Documentation under `docs/` must be written in English.
- Use `.cursor/skills/technical-writer/SKILL.md` before creating, editing,
  translating or reviewing technical documentation.
- Use `.cursor/skills/diagram-drawer/SKILL.md` before creating, editing or
  reviewing Mermaid/Draw.io diagrams.
- Use `.cursor/skills/presentation-maker/SKILL.md` before creating or refining
  high-level technical/strategy presentations from `~/Downloads/Presentation.odp`.

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
- Galaxion Billing V1 : utiliser `billing-api`, pas `billing-service` (plus utilise). La recuperation de facture passe par `GET /bill-run-documents/search` puis `GET /bill-run-documents/{document_id}/download`.
- Aucun endpoint Galaxion identifie ne fournit les lignes facture structurees pour la V1 ; le detail facture doit venir du PDF via un `InvoicePdfExtractor` deterministe avant comparaison.

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
| Mermaid labels on wrong arrows | Put labels such as `retrieval` and `generation` on the edge where the real interaction happens, typically adapter -> PgVector or adapter -> external LLM, not on ambiguous internal backend handoffs. |
| Draw.io detached arrows | Use explicit `exitX/exitY` and `entryX/entryY` anchors for important labeled edges, especially inside or across swimlanes. |
| Supposer que `billing-service` est la source facture Galaxion | `billing-service` n'est plus utilise ; cibler `billing-api` uniquement pour Billing. |
| Utiliser `invoices/composed` comme detail facture client | Ce n'est pas le chemin retenu V1. Recuperer le PDF via `bill-run-documents` puis extraire un JSON facture structure avant le moteur de comparaison. |
| ODP template slides stayed visually blank despite text in `content.xml` | Do not keep patching ODP placeholders blindly. Generate a PPTX with standard PowerPoint text shapes (e.g. via `python-pptx` in a temp venv) when no LibreOffice renderer is available. |
| Presentation content overflowed template frames | For `Presentation.odp`, prefer simple large layouts, one idea per slide, and two short bullets max; do not fill every placeholder just because it exists. |
