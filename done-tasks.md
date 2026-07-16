# Done tasks

> **Scope: Voice Support Bot only.** This is the ledger for all `voice-support-bot`
> work. Do not log bot work in the workspace-root `BMad/done-tasks.md`.

## 2026-06-22 — Agent name badges, conversation fixes, dead code cleanup

**Summary:**

- Fixed conversation history bug where the LLM repeated greetings after every message — `buildHistory()` was including the current user turn, so history was never empty on first message and the question was duplicated in the prompt
- Added `agentName` propagation through the full stack: backend `StreamingResult` / `ConversationResponse` → SSE `done` event → Python bridge `answer_done` WebSocket message → frontend `VoiceChat` message model
- Implemented colored agent name badges in `MessageList.tsx` — each assistant message displays the responding agent's name (blue for Support Technique, green for Facturation, orange for Commercial)
- Ran full-repository Bugbot review and fixed all flagged issues: domain vector search excluding legacy chunks without `domain` metadata, `IntentClassifier` arbitrary tie-breaking, keyword matching false positives (substring `"ip"` matching `"équipement"`), React `setState` during render, bridge Python camelCase field name mismatch, missing SSE error event handling, missing HTTP response status checks, audio queue not stopping current source on clear
- Removed 504 lines of dead legacy voice pipeline code: Deepgram STT adapter, Piper TTS adapter, backend WebSocket handlers, voice controller, voice config, WebSocket config, and associated ports
- Updated architecture diagrams (draw.io)

### Files changed
- `backend/.../service/ConversationOrchestrator.java` — agentName in StreamingResult/ConversationResponse, fixed buildHistory() to exclude current turn
- `backend/.../adapter/in/rest/StreamingConversationController.java` — agentName in SSE done event JSON
- `backend/.../adapter/in/rest/ConversationController.java` — agentName in AskResponse
- `backend/.../service/IntentClassifier.java` — session-sticky tie-breaking, word-boundary keyword matching
- `backend/.../service/GuardrailService.java` — word-boundary keyword matching
- `backend/.../adapter/out/pgvector/PgVectorStoreAdapter.java` — default domain metadata, expanded search filter
- `bridge/bridge_server.py` — agentId/agentName propagation, SSE error handling, snake_case field fix
- `frontend/src/features/voice-chat/VoiceChat.tsx` — agentName on messages, setState fix
- `frontend/src/features/voice-chat/MessageList.tsx` — colored agent name badges
- `frontend/src/features/voice-chat/useVoiceWebSocket.ts` — agentName callback param
- `frontend/src/features/voice-chat/useAudioQueue.ts` — source.stop() on clear
- Deleted: `DeepgramSttAdapter`, `PiperTtsAdapter`, `VoiceWebSocketHandler`, `TwilioMediaStreamHandler`, `VoiceController`, `VoiceConfig`, `WebSocketConfig`, `SpeechToTextPort`, `TextToSpeechPort` (504 lines removed)

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

## 2026-06-24 — Knowledge-base draw.io diagram fixes

**Summary:**

- Fixed the knowledge-base architecture diagram where arrows rendered "detached" from boxes and labels were misplaced — root cause was nodes nested in swimlanes (relative coords) combined with edges lacking fixed anchor points
- Rebuilt every edge with explicit `exitX/exitY` + `entryX/entryY` anchor fractions so arrows glue to precise box borders and labels sit on the segment
- Re-laid the diagram to minimise edge crossings (boxes routed through clear lanes) and kept the color convention (green = PostgreSQL/pgvector links, red = external AI calls, dashed = future connectors)
- Per user request, converted the three zones (`Sources KB`, `Backend Java`, `PostgreSQL + pgvector`) into proper draw.io **swimlanes** with nodes nested inside, recomputing child coordinates relative to each swimlane origin (accounting for the `startSize=30` title bar)
- Validated XML well-formedness with the Python minidom parser after each edit

### Files changed
- `docs/diagrams/knowledge-base.drawio` — rebuilt with anchored edges and swimlane zones

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

## 2026-07-08 — Functional specification and omnichannel strategy

**Summary:**

- Created a functional specification for Voice Support Bot covering business context, scope, stakeholders, user journeys, functional/non-functional requirements, handled data, MVP acceptance criteria, and roadmap.
- Added WhatsApp/messaging as a future omnichannel channel that must reuse the same conversation backend, KB, guardrails, multi-agent routing, and escalation rules.
- Clarified the industrialization strategy: start with the current stack for speed and control, while keeping the option to integrate Genesys Cloud CX later as a contact-center layer for channels, queues, agent desktop, supervision, and human handoff.
- Captured the architectural boundary: Genesys/WhatsApp should not replace the Java conversation engine; RAG, business rules, guardrails, routing, and persistence remain in the backend.

### Files changed
- `docs/product/cahier-des-charges-fonctionnel.md` — new functional specification with WhatsApp and Genesys Cloud CX readiness.
- `CLAUDE.md` — added omnichannel and Genesys Cloud CX architecture notes.
- `AGENTS.md` — added common mistake warning about not moving conversation-engine responsibilities into channel/contact-center integrations.

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

## 2026-07-10 — STT validation sprint (US-036 pipeline timing, real fixtures, live Gradium run)

**Summary:**

- **US-036 — voice-journey timing by pipeline slice:** built `PipelineTimingReport` that aggregates latency spans into six canonical journey slices (channel ingress → end-of-turn → STT request → backend first token → TTS first audio → channel egress) with p50/p95/p99 per slice. Un-instrumented slices are emitted explicitly as `"measured": false` with a reason/owning ticket so a gap can never be read as a fast slice. Added a `pipeline_timing_cli`, unit tests, and a Behave scenario. Requalified as done for the STT scope.
- **Real STT fixtures (TASK-STT-007):** replaced the ASCII placeholder `.wav` files (19–33 bytes) with real **raw PCM16 mono 16 kHz** audio generated by `generate_fixtures.py` (macOS `say` → strip WAV header via `wave.readframes()`), across short / long / accented / noisy / silence categories (noisy = synthetic white-noise mix, accented = `fr_CA` voice as proxies). Fixtures are now `.pcm`; the `.txt` transcript sidecars are unchanged.
- **First live Gradium run:** ran the quality CLI over the real fixtures with the key from `.env`, capturing per-category WER + real latency. Confirmed Gradium wants raw PCM (not a WAV container) and that batch latency scales with clip length (~1.1 s / 1 s → ~2.7 s / 4.3 s).
- **RF-008 / TASK-STT-011 opened:** live run exposed that the raw whitespace WER over-penalizes correct transcripts (punctuation/case/accents count as errors, e.g. WER 1.0 for `Bonjour` vs `Bonjour.`). Normalization before scoring is required before the quality gate is meaningful.
- **Backlog hygiene:** reintegrated the missing TASK-STT-008 (Gradium provider) into the sprint; recorded streaming follow-ups (TASK-STT-009 end-of-turn/VAD, TASK-STT-010 partial STT, TASK-WEB-004 incremental TTS) as out-of-sprint follow-ups mapped to the pipeline slices/findings they close.
- Merged all feature branches (US-036, TASK-STT-007/008, backlog updates) into `feat/restart-from-scratch` fast-forward; deleted the obsolete US-019 branch.

### Files changed
- `voice-agent/stt_validation/pipeline_timing.py` — canonical-slice latency report with explicit gap reporting.
- `voice-agent/stt_validation/pipeline_timing_cli.py` — CLI replaying fixtures → JSON timing report.
- `voice-agent/tests/test_pipeline_timing.py` — unit tests (slice precedence, gap reporting, serialization).
- `voice-agent/features/pipeline_timing.feature` (+ steps) — Behave scenario for US-036.
- `voice-agent/fixtures/generate_fixtures.py` — generates raw PCM16 16 kHz fixtures.
- `voice-agent/fixtures/**/*.pcm` + `manifest.json` — real audio fixtures replacing placeholders.
- `docs/qa/stt-transcription-quality.md` — recorded first live Gradium per-category run + RF-008.
- `product-backlog/**` — sprint, tasks, findings and story traceability updates.

## 2026-07-10 — STT Sprint 2 hardening (TASK-STT-011/007/005) + review remediation

**Summary:**

- **TASK-STT-011 — WER normalization:** added `normalize_transcript` (lowercase, strip punctuation, fold accents via NFKD) applied before `word_error_rate`, so the quality gate stops penalizing punctuation/case/accent artifacts. Live re-run: `short` WER 1.00→0.00, `long` 0.083, `accented` 0.182 pass; only `noisy` fails on a genuine error. Closed RF-008.
- **TASK-STT-007 — multi-sample fixtures + per-category reporting:** expanded to 5 samples per usable category (+2 silence), added `CategorySummary` aggregation and `MIN_SAMPLES_FOR_PERCENTILES=5` significance flag, and padded fixture onsets with silence to avoid first-word clipping. Closed RF-005.
- **TASK-STT-005 — sanitization hardening:** `_redact_token` now also redacts bare filenames (`<redacted-file>`) and identifier-like tokens (`<redacted-id>`: UUID, secret prefixes, ≥7-digit runs, mixed ids). Closed RF-001.
- **Adversarial review remediation (RF-009/010/011):** added a `_SAFE_TOKENS` allowlist so technical tokens (`pcm_16000`, `audio/pcm`) stay readable; added a manifest↔sidecar drift-guard test; excluded unusable categories from the significance aggregate.
- Per-ticket branches merged into `feat/sprint-2-stt-hardening`; RF remediation on `task/sprint-2-review-remediation`.

### Files changed
- `voice-agent/stt_validation/quality.py` — `normalize_transcript`, `CategorySummary`, significance aggregate excluding unusable categories.
- `voice-agent/stt_validation/sanitization.py` — bare filename/id redaction + `_SAFE_TOKENS` allowlist.
- `voice-agent/fixtures/generate_fixtures.py` + `manifest.json` — 22-sample padded fixture set.
- `voice-agent/tests/test_quality.py`, `test_manifest.py`, `test_sanitization.py` — coverage for aggregation, drift guard, redaction.
- `docs/qa/stt-transcription-quality.md`, `docs/observability/stt-validation-telemetry.md` — updated runs + sanitization notes.
- `product-backlog/review-findings.md`, `sprints/`, `tasks/`, `backlog-index.md` — statuses and RF dispositions.

## 2026-07-10 — Knowledge base reorganization + generalize-knowledge skill fix

**Summary:**

- Discovered this repo's `generalize-knowledge` skill was a verbatim copy of the workspace-root one still targeting "workspace root" — so Voice Support Bot learnings were being written into the sibling `BMad` repo instead of here. Rewrote the skill to target `voice-support-bot/{CLAUDE.md,AGENTS.md,done-tasks.md}` explicitly (with a "write to this repo only" table); scoped the root skill to BMad/`cursor-usage-dashboard` and made it redirect bot work here.
- Repatriated all Voice Support Bot knowledge that had leaked into the `BMad` root files: 4 done-task entries, a runtime-architecture section + 16 `CLAUDE.md` "Issues" rows, and 13 `AGENTS.md` common-mistake bullets (including all draw.io guidance). Generic cross-project knowledge (React `setState`, Grep cross-check, sprint hygiene) stayed in root.
- Marked this repository self-contained for AI guidance: notes in `CLAUDE.md`/`AGENTS.md` plus an "Authoritative docs & skills" section in the workspace-root `.cursor/rules/voice-support-bot.mdc`, so bot work uses only this repo's docs and `.cursor/skills/`.
- Merged the Sprint 2 branches into `feat/sprint-2-stt-hardening`: `chore/self-contained-guidance` (fast-forward) and `task/sprint-2-review-remediation` (RF-009/010/011, no-ff). 75 unit tests + 8 behave scenarios green after merge.
- Learned: `voice-support-bot` is a separate nested git repo — git operations must run from inside it, and a reverted working tree can silently drop committed content (verify against HEAD before appending to knowledge files).

### Files changed
- `.cursor/skills/generalize-knowledge/SKILL.md` — retargeted to this repository's own knowledge files.
- `CLAUDE.md`, `AGENTS.md`, `done-tasks.md` — self-contained notes + repatriated Voice Support Bot knowledge; new nested-repo / working-tree pitfalls.

## 2026-07-13 — Sprint 2 completion (TASK-STT-006 + TASK-STT-009) + sprint closure

**Summary:**

- **TASK-STT-006 — dedicated `UNAVAILABLE` STT outcome:** added `SttOutcome.UNAVAILABLE` and a `NoSpeechDetectedError` raised by the fixture and Gradium providers on an empty transcript, mapped in `SttValidationRunner` to a distinct outcome/telemetry (no invented transcript) and recognized by the quality harness. Distinguishes "no usable speech" from a genuine failure. Validated live on Gradium: the two silence fixtures return `unavailable` / `no_speech` with an empty transcript.
- **TASK-STT-009 — end-of-turn detection + instrumentation (US-036 `end_of_turn` slice):** added `EndOfTurnDetector` (authoritative trailing-silence window over PCM16 with an explicit `client_stop` fallback, endianness-safe), wired into `WebVoiceIngress` to emit the `voice.end_of_turn` span + `detected`/`absent` events, and registered the slice in `pipeline_timing`. Streaming VAD upgrade ticketed as **TASK-STT-012** (Sprint 4) as a drop-in replacement.
- **Live Gradium validation (real API key from `.env`):** full 22-fixture quality run (real transcripts, per-category WER, latency p50≈2.3s/p95≈3.1s) and full web-voice-ingress run driving `WebVoiceIngress` + real Gradium — all three implemented slices (`channel_ingress`, `end_of_turn`, `stt`) measured end to end.
- **Quality threshold:** briefly recalibrated 0.8→0.7 against the live run, then reverted to **0.8** — the fixtures are synthetic, so the strict target stays as a reference; recalibration deferred until real human recordings exist (TASK-STT-007 residual). The gate is legitimately `ready: false` on synthetic noisy audio.
- **Sprint closure:** validated by the user; `feat/sprint-2-stt-hardening` merged fast-forward into `feat/restart-from-scratch` (88 unit + 8 behave green), sprint branch deleted, `feat/restart-from-scratch` pushed to origin.

### Files changed
- `voice-agent/stt_validation/models.py`, `providers.py`, `gradium_provider.py`, `runner.py`, `quality.py` — `UNAVAILABLE` outcome + `NoSpeechDetectedError`.
- `voice-agent/web_voice/end_of_turn.py` (new), `ingress.py` — end-of-turn detector + span/event emission.
- `voice-agent/stt_validation/pipeline_timing.py` — `voice.end_of_turn` slice registration.
- `voice-agent/tests/test_end_of_turn.py` (new), `test_web_voice_ingress.py`, `test_pipeline_timing.py`, `test_gradium_provider.py`, `test_stt_validation_runner.py`, `test_quality.py` — coverage.
- `product-backlog/` — TASK-STT-006/009 marked Done, TASK-STT-012 added (Sprint 4), Sprint 2 status closed, backlog-index registry updated.
- `docs/observability/`, `docs/qa/` — telemetry + QA doc updates for the new outcome and slice.

## 2026-07-13 — Sprint 3: TTS voice-out (TASK-WEB-002)

**Summary:**

Delivered the **voice-out half** of US-019: turn response text into speech via a Gradium TTS provider and play it back in the web page, closing the first visible **voice-in → voice-out echo loop**. Built as a strict architectural mirror of the STT half, with a hard boundary between the two.

### What shipped (ST-1 → ST-8, adversarial review after each)
- **ST-1 — Gradium TTS spike:** live WebSocket probe locked the contract (`wss://api.gradium.ai/api/speech/tts`, base64 PCM chunks until `end_of_stream`); documented in `docs/qa/gradium-tts-contract.md`. Surfaced that `GRADIUM_VOICE_ID=default` is rejected — a real catalog voice id is required.
- **ST-2 — TTS provider layer:** `tts_synthesis` package — `TtsOutcome`/`SynthesisResult` models, `TtsProvider` protocol + `EmptyTextError`, deterministic `FixtureTtsProvider` (generated tone keyed by text length; no committed binary clips).
- **ST-3 — `GradiumTtsProvider` + factory:** WebSocket-based provider with an injectable transport (async wrapped synchronously); unit tests cover success/invalid-voice/credit/auth/timeout/no-audio with no network and assert the API key never reaches an exception, log or telemetry.
- **ST-4 — Runner + shared extraction:** `TtsSynthesisRunner` mirroring the STT runner (telemetry + sanitized errors). Extracted telemetry + sanitization into a **neutral `voice_common/` package** imported by both halves; `stt_validation` telemetry/sanitization became re-export shims. Registered `voice.tts.first_audio` + `web.voice.egress` slices in the pipeline-timing aggregator.
- **ST-5 — Web egress + `POST /api/voice/tts`:** `WebVoiceEgress` (synthesis → PCM → 44-byte WAV via `pcm_to_wav`) returns `audio/wav` on success, sanitized JSON on failure; `web.voice.egress` span measured on the **real send window** (span emission split from synthesis so the transport times the actual socket write). `MAX_TTS_TEXT_CHARS` guard.
- **ST-6 — Frontend echo loop:** after STT success, `app.js` POSTs the transcript to `/api/voice/tts`, `decodeAudioData`s the WAV, plays it via a single `AudioBufferSourceNode` on a dedicated playback context; `stopPlayback()` guards the "stop source on clear" pitfall. Validated live via Chrome DevTools MCP (decode 2.04 s mono, TTFA ~109 ms, correlation id propagated, sanitized failure path, clean console).
- **ST-7 — Architecture separation test:** AST import scan fails if `tts_synthesis` imports `stt_validation.*` or vice versa (relative + `voice_common` allowed); includes a self-test proving the detector flags a synthetic cross-import.
- **ST-8 — QA + docs:** `features/tts_synthesis.feature` (synthesize→audio→slice, empty→unavailable, failure sanitized with a secret-leak assertion) + extended `pipeline_timing.feature` (full-turn sample proving TTS slices become measured, only `backend_first_token` remains a gap); `fixtures/tts/reference-texts.txt`; updated `docs/observability/voice-journey-timing.md` + `voice-agent/README.md`.

### Post-review follow-ups (same sprint, before merge)
- **`pipeline_timing` moved to `voice_common`** (canonical, neutral) with a re-export shim at `stt_validation.pipeline_timing`, so both halves build the same per-slice report; separation test hardened to assert `voice_common` neutrality.
- **`TtsSynthesisRunner` refactored** (span/result/record helpers, methods ≤ 20 lines) and a latent **`asyncio` scope bug** on the live Gradium path fixed (module-level import + extracted `_recv_until_end`), covered by a new fake-WebSocket live-path test.
- **`websockets` pin widened** `>=13,<16` → `>=13,<17` to match the tested/demoed runtime (16.1).

### Boundary + tests
- **Hard STT/TTS separation:** neither package imports the other; shared code lives in `voice_common`, enforced by `tests/test_architecture_separation.py` (both directions + `voice_common` neutrality).
- **130 unit tests green; 4 behave features / 12 scenarios green.** Echo loop MCP-validated; live Gradium voice-out demo validated by the user (full voice→voice turn traced under one correlation id).
- **Merged (fast-forward) into `feat/restart-from-scratch`** after the user validated the live demo.

### Key files
- `voice-agent/tts_synthesis/` — `models.py`, `providers.py`, `gradium_tts_provider.py`, `provider_factory.py`, `runner.py`
- `voice-agent/voice_common/` — `telemetry.py`, `sanitization.py`, `pipeline_timing.py` (neutral shared; `pipeline_timing` registers the TTS slices)
- `voice-agent/web_voice/egress.py` + edits to `server.py`, `__init__.py`, `static/app.js`, `static/index.html`
- `voice-agent/stt_validation/pipeline_timing.py` — re-export shim over `voice_common.pipeline_timing`
- `voice-agent/tests/` — `test_tts_providers.py`, `test_gradium_tts_provider.py`, `test_tts_runner.py`, `test_web_voice_egress.py`, `test_architecture_separation.py`
- `voice-agent/features/tts_synthesis.feature` + `steps/tts_steps.py`; extended `pipeline_timing.feature` + steps
- `voice-agent/fixtures/tts/reference-texts.txt`; `voice-agent/scripts/gradium_tts_spike.py`
- Docs: `docs/qa/gradium-tts-contract.md`, `docs/observability/voice-journey-timing.md`, `voice-agent/README.md`
- Planning: `product-backlog/sprints/sprint-3-tts-voice-out.md`, `product-backlog/tasks/web-voice-tasks.md`, `product-backlog/backlog-index.md`

## 2026-07-14 — Sprint 4: Pipecat batch runtime migration (TASK-WEB-005)

**Summary:**

Ran the existing web voice **batch** loop (STT → echo → TTS) through a **Pipecat pipeline**, aligning the runtime with the ADR-0002 target and de-risking the framework migration **before** streaming (Sprint 6). Migration / de-risking sprint, **not** a latency sprint: batch-on-Pipecat is not expected to beat batch-on-stdlib. User-visible behaviour is unchanged (the browser keeps its two-call echo loop) and the same US-036 slices stay observable. Streaming STT/TTS/VAD + the WebRTC transport are Sprint 6 (the backend answer bridge TASK-WEB-003 is Sprint 5).

### What shipped (ST-1 → ST-9, each committed)
- **ST-1 — Pipecat spike + dependency pin:** `pipecat-ai>=1.5,<2` pinned; a throwaway `scripts/pipecat_spike.py` locked the batch frame/runner API (frame types, `EndFrame`, driving a pipeline to completion off a transport). Findings in `docs/qa/pipecat-batch-contract.md`. Locked the deprecated `PipelineTask`/`PipelineRunner` pair (the newer `WorkerRunner` hung on frames queued before it went live) with the DeprecationWarning suppressed locally, pending the Sprint 6 streaming migration.
- **ST-2 — Gradium STT as a Pipecat service:** `voice_pipeline/stt_service.py` — `SttFrameProcessor` consuming a whole-utterance `InputAudioRawFrame`, delegating to an injected STT ingress (duck-typed `SttIngress`), emitting a `TranscriptionFrame`. Never invents a transcript on non-success. Imports `stt_validation` + pipecat only.
- **ST-3 — Gradium TTS as a Pipecat service:** `voice_pipeline/tts_service.py` — `TtsFrameProcessor` consuming a plain `TextFrame`, delegating to an injected egress, emitting a `TTSAudioRawFrame`; forwards `TranscriptionFrame` (a `TextFrame` subclass) untouched. Imports `tts_synthesis` + pipecat only.
- **ST-4 — Echo processor + in-memory batch pipeline:** `voice_pipeline/echo.py` (transcript → plain text, domain-neutral) and `voice_pipeline/pipeline.py` composing `stt → echo → tts → capture-sink` with `run_batch_turn` / `run_stt_turn` / `run_tts_turn` helpers driven in memory (no transport).
- **ST-5 — Telemetry bridge:** the Pipecat services thread the same `TelemetryRecorder` into the same `WebVoiceIngress`/`WebVoiceEgress`, so the four US-036 slices (`web.voice.ingress`, `stt.request`, `voice.tts.first_audio`, `web.voice.egress`) stay measured. `PipelineTelemetryBridgeTest` in `test_pipeline_timing.py` proves it end to end.
- **ST-6 — Runtime seam + `--runtime` + `POST /api/voice/turn`:** `VoiceTurnProcessor` protocol in `web_voice/runtime.py` with `StdlibTurnProcessor` (direct ingress/egress) and `PipecatTurnProcessor` (drives the pipeline); `main()` adds `--runtime {stdlib,pipecat}` (env `VOICE_RUNTIME`). New `POST /api/voice/turn` runs the whole loop server-side in one call. Both legacy endpoints keep their exact contract on either runtime. Frontend untouched.
- **ST-7 — Architecture separation extended:** `test_architecture_separation.py` now asserts `voice_pipeline/stt_service.py` never imports `tts_synthesis`, `tts_service.py` never imports `stt_validation`, neither pulls `web_voice`, and `echo.py` stays domain-neutral.
- **ST-8 — A/B parity harness:** `scripts/ab_parity.py` runs the same input through both runtimes (providers held constant), asserts byte-identical WAV and reports per-runtime latency (Pipecat adds ~2 ms p50 steady-state overhead, as expected for batch).
- **ST-9 — Flipped default to `pipecat` + behave both runtimes + docs/ADR:** `DEFAULT_RUNTIME = PIPECAT` (stdlib stays selectable); behave scenarios exercise the Pipecat path + cross-runtime parity; updated `README`, `docs/observability/voice-journey-timing.md`, ADR-0002 branch note and the `architecture.md` caveat.

### Adversarial review (retroactive, full-diff)
- Ran the project `adversarial-code-review` skill over the whole TASK-WEB-005 diff (it had been skipped per-ST). **Verdict Proceed, 94/100, QA gate Pass**, no blocking findings.
- Closed the one test gap by adding an HTTP-layer 502 test for `/api/voice/turn` (fails closed with JSON + correlation id, no WAV, on both runtimes).
- Logged non-blocking findings: **RF-012** (`asyncio.run` per request — gated to the Sprint 6 async transport), **RF-013** (raw provider `error_reason` echoed in the 502 body → ticketed **TASK-WEB-006**), **RF-014** (`/turn` extends the unauthenticated ingress surface — same gating as RF-006).

### Tests + merge
- **156 unit tests green; 4 behave features / 14 scenarios green.** Live boot smoke test confirmed both runtimes serve `/` and route `/api/voice/turn` identically. Full browser MCP echo-loop re-validation stays a manual QA step (needs a live mic + Gradium key).
- **Merged (fast-forward) into `feat/sprint-4-pipecat-batch` then `feat/restart-from-scratch`**, both pushed to origin.

### Key files
- `voice-agent/voice_pipeline/` — `__init__.py`, `stt_service.py`, `tts_service.py`, `echo.py`, `pipeline.py`
- `voice-agent/web_voice/runtime.py` (seam) + edits to `web_voice/server.py` (`--runtime`, `/api/voice/turn`)
- `voice-agent/requirements.txt` (`pipecat-ai>=1.5,<2`); `voice-agent/scripts/pipecat_spike.py`, `scripts/ab_parity.py`
- `voice-agent/tests/` — `test_stt_service.py`, `test_tts_service.py`, `test_pipeline.py`, `test_voice_runtime.py`, `test_ab_parity.py`, extended `test_pipeline_timing.py` + `test_architecture_separation.py`
- `voice-agent/features/web_voice.feature` + `steps/web_voice_steps.py`
- Docs: `docs/qa/pipecat-batch-contract.md`, `docs/observability/voice-journey-timing.md`, `docs/architecture/architecture.md`, `docs/architecture/adrs/ADR-0002-...md`, `voice-agent/README.md`
- Planning: `product-backlog/sprints/sprint-4-pipecat-batch.md`, `product-backlog/tasks/web-voice-tasks.md` (TASK-WEB-005 Done, TASK-WEB-006 opened), `product-backlog/backlog-index.md`, `product-backlog/review-findings.md`

## 2026-07-15 — Sprint 5: Backend answer bridge (TASK-WEB-003, US-019 close) + sprint closure

**Summary:**

Turned the web voice **echo** loop into a real **answer** loop: the STT transcript is routed to a replaceable conversation backend, the response text is spoken back through TTS, all under one correlation id from ingress to egress. Closes **US-019** and the last **US-036** gap (`backend_first_token`). The `US-003` boundary is preserved — the backend owns the answer, the voice runtime owns the media. Not a billing-reasoning sprint (the answer engine is a placeholder gated by OQ-007) and not a latency sprint (streaming stays Sprint 6).

### What shipped (sub-tickets A–G, adversarial review + commit each)
- **A — Conversation contract + `BackendAnswerPort`** (review 96/100): neutral `conversation_backend/` package — `BackendAnswerPort`, `AnswerRequest`/`AnswerResult`, `AnswerOutcome`, `EmptyTranscriptError`; privacy-safe `to_dict` (lengths only, never raw text). Stays isolated from `stt_validation`/`tts_synthesis`/`web_voice`.
- **B — Stub backend adapter** (review 96/100): deterministic, digit/currency-free answer (DEC-002), default for dev/tests.
- **C — HTTP backend adapter + `--backend {stub,http}`** (review 93/100, resolves RF-016): `HttpBackendAdapter` posts JSON to `VOICE_BACKEND_URL` with an injectable transport (stdlib `urllib` default); maps `text`/`answer` + optional `confidence`; every fault → sanitized degraded; API key lives only in `x-api-key`. Selection via `build_backend` / env `VOICE_BACKEND`.
- **D — Wire the bridge** (review 93/100): the answer step replaces the echo on both runtimes (stdlib + pipecat), byte-identical output.
- **E — End-to-end telemetry** (review 95/100, user-validated): `backend.request` + `backend.first_token` spans registered as the US-036 `BACKEND_FIRST_TOKEN` slice; one correlation id ingress→stt→backend→tts→egress.
- **F — Degraded mode** (resolves RF-020): backend unavailable / low confidence (`< 0.5`) / empty answer → a fixed, digit-free safe spoken fallback and a `degraded` outcome; only an empty transcript stays silent. One policy in `voice_pipeline/answer.py` for both runtimes.
- **G — QA + docs + ADR + latency** (review 95/100): documented the two previously code-only contracts and added QA/latency evidence.

### Live validation (user)
- Ran the app with the real Gradium key from `.env`: real Gradium **STT + TTS**, `runtime=pipecat`, first with **`--backend stub`**, then with **`--backend http`** against a throwaway local mock conversation endpoint (ADR-0021 wire shape). User validated the full Voice2Voice loop and the degraded outcomes (`low_confidence`, `empty_answer`, `backend_unavailable`). The mock was a `/tmp` dev aid, not committed. Live browser JS re-validation (RF-019) remains a manual step.

### Tests + closure
- **211 unit tests green; 5 behave features / 17 scenarios green.** Repeatable full-turn per-slice sample (`scripts/turn_latency_sample.py`) measures all six US-036 slices on success and degraded paths (offline/fixture numbers; live latency gated on the real endpoint).
- **Merged (fast-forward) into `feat/restart-from-scratch`** and pushed. Sprint status flipped to ✅ Done in the sprint file, roadmap and `backlog-index.md` registry; US-019 + TASK-WEB-003 marked Done.
- Non-blocking findings gated: **RF-015** (confidence not range-validated → OQ-002), **RF-019** (no frontend JS test → manual QA), **RF-021** (`first_token`==`request` until a streaming backend), **RF-006/RF-014** (unauthenticated ingress → OQ-001).

### Key files
- `voice-agent/conversation_backend/` — `port.py`, `models.py`, `stub_backend.py`, `http_backend.py`, `degraded.py`, `backend_factory.py`
- `voice-agent/voice_pipeline/answer.py` (shared answer step + degraded policy + telemetry); edits to `web_voice/server.py` (`--backend`, `/api/voice/turn` answer + `X-Answer-*` headers) and `web_voice/runtime.py`
- `voice-agent/scripts/turn_latency_sample.py`; `voice-agent/tests/` — `test_conversation_backend_contract.py`, `test_answer_processor.py`, `test_stub_backend_adapter.py`, `test_http_backend.py`, `test_backend_factory.py`, `test_turn_latency_sample.py`
- `voice-agent/features/` — `conversation_backend.feature` + steps; answer/degraded/parity scenarios in `web_voice.feature`
- Docs: `docs/architecture/voice-runtime-http-contract.md`, `docs/architecture/adrs/ADR-0021-conversation-backend-answer-contract.md`, `docs/qa/web-voice-backend-bridge-qa-report.md`, `docs/observability/voice-journey-timing.md`, `docs/README.md`, `voice-agent/README.md`
- Planning: `product-backlog/sprints/sprint-5-backend-bridge.md`, `product-backlog/backlog-index.md`, `product-backlog/review-findings.md`

## 2026-07-16 — Sprint 6: Barge-in (TASK-WEB-008, slices 1–3 + e2e + adversarial review)

**Summary:**

Implemented barge-in (US-021) so the customer can interrupt the spoken answer, on the
live streaming WebRTC path. Key architectural finding: in **pipecat 1.5.0** the VAD is
**not** auto-wired to the transport (no `vad_analyzer` on `TransportParams`, no
`VADAnalyzer` consumer) — `SileroVADAnalyzer` is a standalone component with the same
integration effort as our energy detector. So we reuse the existing
`StreamingEndOfTurnDetector` for onset and Pipecat's **native** `InterruptionFrame`
mechanism for the cut (ADR-0025). Silero deferred as a drop-in verdict upgrade.

### What shipped
- **Slice 1 — graceful drain** (committed earlier this branch): `StreamingVoiceSession.drain()` queues an `EndFrame` on a graceful `closed`/`disconnected` event so a trailing partial utterance is finalized instead of dropped; wired from `WebRtcSignalingService` cleanup.
- **Slice 2 — barge-in core:** `StreamingSttProcessor` tracks bot-speaking from the `BotStarted/StoppedSpeakingFrame` the output transport emits **upstream**; on speech onset while the bot speaks it calls `broadcast_interruption()` (flushes the output buffer + cancels the TTS task) and emits `voice.barge_in.detected` + `voice.barge_in.count`. `StreamingTtsProcessor` made interruptible: on `CancelledError` → `interrupted` outcome (`tts.interrupted`) + guaranteed WebSocket release via `finally`/`_safe_aclose`.
- **Adversarial review (slice 2):** score 87→~92 after fixes. Blocking finding fixed: an interrupted turn no longer skews the `tts_first_audio` p95 — `voice.tts.first_audio` is emitted with the real time-to-first-audio and only when audio actually played; elapsed moves to the `tts.interrupted` event.

### What shipped (slice 3 + e2e, added after the slice-2 entry above)
- **Slice 3 — echo cancellation:** the WebRTC client sets `echoCancellation` + `noiseSuppression` + `autoGainControl` on `getUserMedia` so the bot's own audio does not re-enter the mic and self-trigger the energy VAD.
- **Behave e2e:** `features/barge_in.feature` drives the composed `[source → streaming STT → streaming TTS → sink]` chain — onset while bot-speaking cuts the in-flight answer (`tts.interrupted`, only the played chunk emitted), broadcasts an `InterruptionFrame`, records `voice.barge_in.detected`/`count`, and still transcribes the new utterance; plus a no-barge-in normal-turn scenario. (A two-phase `queue_frames` harness deadlocked — the internal `InterruptionFrame` cancels the whole `PipelineTask`; reverted to the single-phase harness the unit tests use.)

### Tests + docs
- Full suite green: **269 unit tests + behave 9 features / 25 scenarios / 114 steps.**
- **ADR-0025** created (barge-in: native `InterruptionFrame` + existing VAD gated by bot-speaking; Silero deferred; echo cancellation required before live validation). Fixed ADR index drift (added ADR-0022..0025 rows).
- Full code + documentation review (2026-07-16): no blocking findings; verified statically that pipecat 1.5.0's base output transport pushes `BotStartedSpeakingFrame` **upstream** (the barge-in pivot).

### Live validation + anti-echo gate (2026-07-16)
- **User live full-stack validation: PASS.** With headphones, barge-in cut the answer cleanly and resumed the new turn; telemetry showed `voice.barge_in.detected` ↔ `tts.interrupted` 1:1, a non-interrupted turn played fully, and the interrupted `voice.tts.first_audio` spans carried the real time-to-first-audio (310/452 ms), not total elapsed — the p95 fix held in live.
- **Bug found live (without headphones): self-interruption from acoustic echo.** Browser `echoCancellation` (slice 3) attenuates but does not remove the bot's own speaker→mic echo, and the energy VAD read the residual as speech. Because the echo is *continuous*, N-frame confirmation alone can't reject it — the discriminating lever is **amplitude**.
- **Fix — anti-echo barge-in gate** (`StreamingSttProcessor`): the cut now requires the incoming frame to exceed a **barge-in amplitude threshold** (default 2500, above the 1000 STT onset threshold) **and** stay above it for a **confirmed run of N frames** (default 4, rejects brief spikes). Both env-tunable (`VOICE_BARGE_IN_THRESHOLD`, `VOICE_BARGE_IN_FRAMES`) via the signaling wiring — no code change to tune an echoey speaker setup. The STT session still opens on normal onset (utterance always captured); only the cut is gated. **Re-validated live by the user: no self-interruption on speakers, real barge-in still cuts.** ADR-0025 updated (decision point 7).
- Tests: +2 anti-echo unit tests (residual echo below threshold → no barge-in; brief spike < N frames → no barge-in). Full suite green: **271 unit + behave 9 features / 25 scenarios / 114 steps**.

### Status
- **Validated by user (2026-07-16); merge-ready on `task/TASK-WEB-008-barge-in` (unmerged — merge on explicit request).**

### Files changed
- `voice-agent/web_voice/streaming_stt_processor.py` — bot-speaking tracking + onset-gated `broadcast_interruption()` + barge-in telemetry
- `voice-agent/web_voice/streaming_tts_processor.py` — interruptible synthesis (`CancelledError` → `interrupted` + `finally` close); TTFA-correct interrupted span
- `voice-agent/web_voice/streaming_runtime.py`, `web_voice/webrtc_signaling.py` — `drain()` on call end (slice 1)
- `voice-agent/web_voice/utterance_aggregator.py` — scope-guard comment (barge-in lives on the streaming STT path)
- `voice-agent/web_voice/static/webrtc.js` — slice 3: `echoCancellation`/`noiseSuppression`/`autoGainControl` on `getUserMedia`
- `voice-agent/features/barge_in.feature`, `voice-agent/features/steps/barge_in_steps.py` — behave e2e (composed STT→TTS barge-in)
- `voice-agent/tests/test_streaming_stt_processor.py`, `test_streaming_tts_processor.py` — barge-in fire/no-fire + interruption cleanup + TTFA-span tests
- `docs/architecture/adrs/ADR-0025-barge-in-native-interruption.md`, `docs/architecture/adrs/README.md`
