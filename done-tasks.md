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
- `docs/product/v1-scope.md` — scope V1 complet et exigences produit/non fonctionnelles.
- `docs/operations/backlog.md` — rappel des prerequis techniques pour la cible `first audio < 700 ms`.
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
- `docs/architecture/diagrams/target-v1-solution.drawio` — diagramme cible editable.
- `docs/product/v1-scope.md` — ajouts sur Gradium/Pipecat, escalade humaine et exigences techniques structurantes.
- `CLAUDE.md`, `AGENTS.md`, `done-tasks.md` — connaissances partagees.

## 2026-07-01 — Galaxion Billing contracts + documentation structure

**Summary:**

- Reorganisation de `docs/` par usage : product, architecture, integrations, knowledge-base, engineering et operations.
- Analyse Galaxion Billing : `billing-service` n'est plus utilise pour la V1 ; la cible Billing est `billing-api` uniquement.
- Decision d'integration : retrouver les documents facture via `GET /bill-run-documents/search`, telecharger via `GET /bill-run-documents/{document_id}/download`, puis extraire le PDF en JSON structure.
- Le LLM ne doit pas calculer les montants depuis le PDF ; un `InvoicePdfExtractor` deterministe doit produire les lignes, montants, preuves et warnings avant le moteur de comparaison.
- Prochaine tache de reprise : obtenir 1-2 PDFs facture anonymises Galaxion, definir le JSON cible d'extraction final et choisir/prototyper l'outil d'extraction PDF.

### Files changed
- `docs/` — arborescence reorganisee et index ajoute.
- `docs/integrations/galaxion/bss-integration-plan.md` — plan BSS mis a jour autour de `billing-api` et des PDFs facture.
- `docs/integrations/galaxion/galaxion-billing-contracts.md` — contrat Billing initial et flux `bill-run-documents`.
- `CLAUDE.md`, `AGENTS.md`, `done-tasks.md` — apprentissages Galaxion et prochaine tache.

## 2026-07-03 — Skills documentation, diagrams and presentation V1

**Summary:**

- Clarification finale de la cible voix V1 : Gradium + Pipecat est le chemin cible, le bridge custom reste legacy/fallback.
- Creation des docs Galaxion manquantes : contrat JSON `InvoicePdfExtractor` et liste priorisee des inputs a demander au BSS.
- Creation de skills locaux : `technical-writer` (docs techniques en anglais), `diagram-drawer` (Mermaid/Draw.io, labels et anchors), `presentation-maker` (decks high-level depuis `Presentation.odp`).
- Generation d'une presentation projet lisible en anglais (`.pptx`) avec scope V1 et deux diagrammes simplifies d'architecture/flux billing.
- Decouverte : patcher directement `Presentation.odp` peut produire un XML contenant du texte mais des slides visuellement vides ; en absence de LibreOffice, privilegier un PPTX genere avec formes texte standard.

### Files changed
- `.cursor/skills/{technical-writer,diagram-drawer,presentation-maker}/` — skills locaux et evals initiales.
- `docs/integrations/galaxion/{invoice-extraction-json.md,missing-inputs.md}` — contrat d'extraction facture et inputs manquants.
- `docs/architecture/architecture.md` — clarification Pipecat cible vs bridge legacy et labels Mermaid.
- `outputs/presentations/voice-support-bot-scope-architecture/` — storyboard et presentation PPTX.
- `CLAUDE.md`, `AGENTS.md`, `done-tasks.md` — connaissances partagees mises a jour.

## 2026-07-08 — Revue adversariale architecture omnicanale

**Summary:**

- Sauvegarde de la revue adversariale de la vision omnicanale : canaux independants, backend Java commun, Genesys/WhatsApp comme adapters et non moteurs metier.
- Score global retenu : 2.8/5 — socle MVP solide mais pas encore plateforme industrialisee sans contrats, SLOs, observabilite et modes degrades.
- Decision structurante : formaliser les contrats canal/backend et le contrat d'escalade avant d'ajouter de nouveaux canaux reels.
- Risques majeurs captures : backend commun comme goulot potentiel, couplage Gradium dans le voice-agent Python, Genesys/WhatsApp encore conceptuels, SLOs non verifiables.

### Files changed
- `docs/architecture/adversarial-architecture-review-2026-07-08.md` — revue adversariale complete, scorecard, risques, questions dures et recommandations.

## 2026-07-08 — Skill adversarial architecture review

**Summary:**

- Creation du skill local `adversarial-architecture-review` pour rejouer une revue contradictoire des choix d'architecture.
- Le skill note la solution sur NFR/SLA, modes de panne, modularite, remplaçabilite des dependances externes et capacite d'industrialisation.
- Le skill force une sortie structuree : verdict, scorecard, risques critiques, questions dures, revue des dependances externes, gaps NFR/SLA et recommandations priorisees.
- Decision : conserver ce skill dans le repo `voice-support-bot`, pas dans le repo parent `BMad`, car il porte les criteres de revue propres au bot vocal.

### Files changed
- `.cursor/skills/adversarial-architecture-review/SKILL.md` — skill local de revue adversariale architecture/NFR/SLA.
- `CLAUDE.md` — apprentissage sur le score 2.8/5 et l'usage du skill.
- `AGENTS.md` — pieges a eviter autour de l'industrialisation omnicanale sans contrats/SLOs.

## 2026-07-09 — Genesys target architecture and latency observability alignment

**Summary:**

- Clarified the target Genesys Cloud CX pattern: Genesys remains the
  contact-center system of record, while the Java backend owns conversation
  intelligence, RAG, billing reasoning, guardrails, escalation policy and handoff
  content.
- Aligned V1 scope, ADR-0020, backlog epics, user stories, open questions and
  decisions with Genesys handoff, optional full Genesys voice routing, barge-in
  and advisor context transfer.
- Added pilot observability requirements: shared correlation id,
  OpenTelemetry-style spans, per-step latency measurement, Genesys Analytics plus
  AI-layer metrics, and p50/p95/p99 reporting before any production SLO claim.

### Files changed
- `docs/architecture/architecture.md` — target Genesys contact-center pattern.
- `docs/architecture/adrs/ADR-0020-genesys-handoff-v1-full-audio-connector-optional.md` — Genesys system-of-record decision and consequences.
- `docs/product/v1-scope.md` — Genesys V1 scope and latency test matrix.
- `product-backlog/` — epics, stories, decisions, open questions and index aligned with the target architecture.
- `CLAUDE.md`, `AGENTS.md`, `done-tasks.md` — shared knowledge updated.

## 2026-07-09 — STT sprint workflow and first scaffold

**Summary:**

- Defined the delivery workflow: one ticket per branch, QA bug ticket template,
  adversarial code review at 90%, OpenTelemetry required for runtime work, and
  no merge without explicit user approval.
- Created the STT validation sprint with existing stories plus
  `TASK-STT-001` to `TASK-STT-004`.
- Completed `US-003` by documenting the channel/runtime/backend/Genesys identity
  boundary and recording user validation.
- Completed `TASK-STT-001` with a minimal Python `voice-agent` scaffold for
  repeatable STT fixture validation, replaceable provider boundary, local
  OpenTelemetry-compatible events/metrics/logs and unit tests.
- Process learning: after user validation, record validation, rerun checks, then
  commit and push the ticket branch automatically; merge remains explicit.

### Files changed
- `docs/operations/development-workflow.md` — delivery workflow and OpenTelemetry gate.
- `.cursor/skills/{qa-functional-latency,adversarial-code-review,skill-creator}/` — QA/review/skill management support.
- `product-backlog/templates/bug-ticket-template.md` — default QA bug ticket format.
- `product-backlog/sprints/sprint-stt-validation.md` and
  `product-backlog/tasks/stt-validation-tasks.md` — STT sprint and technical tasks.
- `docs/architecture/channel-identity-boundary.md` — accepted boundary for
  channel identity and responsibilities.
- `voice-agent/stt_validation/` and `voice-agent/tests/test_stt_validation_runner.py` — STT fixture validation scaffold and tests.
