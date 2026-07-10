# Repository context for Claude (and similar assistants)

**Voice Support Bot** — V2V (voice-to-voice) RAG voice agent for Telecom/ISP support.

> This repository (`voice-support-bot`) is a **separate git repository** (default branch `main`) nested in the `BMad` workspace. Bot commits belong here, not in the `BMad` repository.

> Self-contained guidance: when working in this repo, use **only** this repository's `CLAUDE.md` / `AGENTS.md` and the skills under `voice-support-bot/.cursor/skills/`. Do **not** apply the workspace-root `BMad/claude.md`, `BMad/agents.md`, or root `.cursor/skills/` (those govern `cursor-usage-dashboard/`).

> Branch note: `feat/restart-from-scratch` intentionally removes the previous
> backend, frontend, voice-agent and Docker Compose implementation. The previous
> code remains preserved on `main` as backup/reference; this branch restarts from
> product scope, architecture decisions, backlog, BSS docs and knowledge-base
> content.

> Delivery rule: no development starts without a ticket. Each user story, bug or
> technical task uses its own branch named after the ticket
> (`us/US-XXX-short-name`, `fix/BUG-XXX-short-name`,
> `task/TASK-XXX-short-name`). The user is the final validator; do not merge any
> branch unless the user explicitly asks for the merge.
> When the user says a ticket is validated, record the validation, rerun checks,
> then commit and push the ticket branch automatically. Merge still requires an
> explicit user request.

## Application layout

| Part | Path | Stack |
|------|------|-------|
| Product backlog | `product-backlog/` | V1 epics, user stories, decisions, open questions |
| Architecture docs | `docs/architecture/` | ADRs, architecture spine, diagrams, reviews |
| Product docs | `docs/product/` | V1 scope and broader functional specification |
| Integration docs | `docs/integrations/` | Galaxion/BSS contracts and missing inputs |
| Knowledge base | `knowledge-base/` | Billing/support/commercial content for future RAG |

The former executable layout (`backend/`, `voice-agent/`, `frontend/`,
`docker-compose.yml`) exists on `main`, not on the restart branch.

## Product scope V1

- V1 targets **end users** and focuses on explaining operator invoice discrepancies.
- The bot must remain an **extensible operator support voice assistant**: billing in V1, then technical support, sales, complaints, retention, or self-care later.
- The **Voice2Voice journey is mandatory**: activation by phone or web voice chat, with text only as a complementary channel.
- The billing source of truth is the **read-only BSS**. The LLM formulates a traceable explanation after deterministic discrepancy calculations; it must not guess amounts.
- The product core must remain agnostic to **LLM / STT / TTS** providers through configurable ports/adapters so several solutions can be benchmarked easily.
- The target V1 voice architecture remains **Gradium + Pipecat** as the current
  reference direction, but implementation must be rebuilt from scratch on the
  restart branch.
- Target Genesys pattern: **Genesys Cloud CX is the contact-center system of
  record** (call ingestion, IVR/ANI, recording, routing, queues, supervision,
  reporting, advisor desktop); the Java backend remains the owner of AI
  conversation workflow, RAG, billing reasoning, guardrails, escalation policy,
  handoff content and conversation memory.
- The V1 product backlog lives in `product-backlog/` (EPICs, user stories, decisions, open questions) so it stays versioned with the application repository before a Jira migration.
- Omnichannel adversarial review (2026-07-08): overall score **2.8/5** — a solid MVP foundation, but not yet an industrialized platform without channel/backend contracts, an escalation contract, measurable SLOs, per-step/channel observability, and tested degraded modes.
- Pilot observability must use a shared correlation id and OpenTelemetry traces,
  metrics and structured logs across Genesys, voice runtime, backend, BSS/PDF
  evidence, comparison, RAG, LLM, TTS and handoff. Report p50/p95/p99 by
  channel/provider before any production SLO claim.
- Every development that touches runtime behavior must add or update the
  OpenTelemetry instrumentation needed for monitoring, QA latency analysis and
  troubleshooting. Missing required traces, metrics or structured logs blocks
  adversarial review and QA acceptance unless the story is explicitly marked as
  not runtime-affecting.
- Use the local `.cursor/skills/product-business/` skill to produce or review PRDs, EPICs, user stories, business rules, and product-level acceptance criteria.
- Use the local `.cursor/skills/adversarial-architecture-review/` skill to challenge architecture choices, NFR/SLA, modularity, external-provider replaceability, and Genesys/WhatsApp/omnichannel readiness.
- Use the local `.cursor/skills/software-architect/` skill for every structural decision and create/update the corresponding ADR in `docs/architecture/adrs/`.
- The editable target diagram is `docs/architecture/diagrams/target-v1-solution.drawio`.
- Documentation under `docs/` must be written in English.
- Use `.cursor/skills/technical-writer/SKILL.md` before creating, editing,
  translating or reviewing technical documentation.
- Use `.cursor/skills/skill-creator/SKILL.md` before creating, modifying,
  evaluating or packaging local agent skills.
- Use `.cursor/skills/qa-functional-latency/SKILL.md` before creating QA
  strategy, Gherkin acceptance tests, Java Cucumber tests, Python Behave tests,
  UI validation plans, pilot readiness reports or latency reports by pipeline
  slice.
- Use `.cursor/skills/adversarial-code-review/SKILL.md` for story-level code
  review before QA acceptance. The developer fixes findings until the review is
  at least 90% satisfied or residual risk is explicitly accepted.
- Use `.cursor/skills/diagram-drawer/SKILL.md` before creating, editing or
  reviewing Mermaid/Draw.io diagrams.
- Use `.cursor/skills/presentation-maker/SKILL.md` before creating or refining
  high-level technical/strategy presentations from `~/Downloads/Presentation.odp`.
- User story delivery follows `docs/operations/development-workflow.md`:
  create or confirm the ticket, create a dedicated branch named after the ticket,
  assign frontend/backend implementation, start QA in parallel, run adversarial
  review until at least 90% satisfied, then QA executes functional and latency
  validation. QA bugs must become explicit bug tickets using
  `product-backlog/templates/bug-ticket-template.md`, then restart the developer
  -> adversarial review -> QA loop. Passing all gates makes a branch
  merge-ready only; merge requires the user's explicit request.

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

## Runtime architecture (conversation engine — implementation preserved on `main`)

> Documents the executable runtime that lives on `main` (removed from
> `feat/restart-from-scratch`). Kept here as the reference the restart rebuilds toward.

- **Multi-agent routing:** `ConversationOrchestrator` routes questions to specialized `AgentProfile`s (Support Technique, Facturation, Commercial) via `IntentClassifier`.
- **Session stickiness:** Each `ConversationSession` tracks the current agent and conversation history. The classifier prefers the current session agent on keyword ties.
- **Guardrail layer:** `GuardrailService` checks input before routing, rejects off-topic or dangerous queries with a canned response.
- **Escalation detection:** `EscalationDetector` identifies requests to speak with a human and returns an escalation response.
- **SSE streaming + POST fallback:** `StreamingConversationController` streams via SSE (including `agentId`/`agentName` in the `done` event JSON); `ConversationController` provides sync POST `/api/conversation/ask`.
- **Voice path:** `voice-agent/agent/bot.py` is the Pipecat target V1 path for WebRTC and Twilio. `bridge_server.py` is a legacy/fallback comparison path only.
- **Frontend agent badges:** Each assistant message bubble displays a colored badge with the responding agent's name (blue=Support, green=Facturation, orange=Commercial).
- **Omnichannel strategy:** Start with the current stack (Pipecat/WebRTC, Twilio, React, Java backend) and keep WhatsApp/messaging as channel adapters that reuse the same conversation backend, KB, guardrails, routing, and escalation rules.
- **Genesys Cloud CX option:** Treat Genesys as a future contact-center layer for channels, queues, agent desktop, supervision, and human handoff. Do not move RAG, business rules, guardrails, or conversation persistence out of the Java backend just because Genesys is introduced.

## API gotchas

- KB endpoints: `POST /api/knowledge/ingest` (one-shot upload) and `POST /api/knowledge/sync` / `/sync/{sourceType}` (connector sync).
- Conversation streaming: `GET /api/conversation/ask-stream` (SSE); sync: `POST /api/conversation/ask`.
- The `domain` (support|billing|commercial) tags each chunk; search filters `domain == X OR general`. Markdown front-matter must match the historical domains (telecom -> support, billing -> billing, commercial -> commercial) to preserve behavior.
- Galaxion Billing V1: use `billing-api`, not `billing-service` (no longer used). Invoice retrieval goes through `GET /bill-run-documents/search`, then `GET /bill-run-documents/{document_id}/download`.
- No identified Galaxion endpoint provides structured invoice lines for V1; invoice detail must come from the PDF through a deterministic `InvoicePdfExtractor` before comparison.

## Testing commands

No application test command exists on `feat/restart-from-scratch` until the new
backend, frontend and voice runtime scaffolds are created. Use `git diff --check`
for documentation-only changes.

Voice runtime STT scaffold:

```bash
cd voice-agent && python3 -m unittest discover tests
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
| draw.io arrows rendered "detached" / floating next to boxes, labels misplaced | Two root causes: (1) nodes nested in swimlanes (`parent="<swimlane>"`) use **relative** coordinates, and (2) edges had **no fixed anchor points** so drawio used floating connections that drift. Fix: give every edge explicit `exitX/exitY/exitDx/exitDy` + `entryX/entryY/entryDx/entryDy` (fractions 0→1 of the box border). Anchored edges stay glued to a precise border point regardless of nesting, and labels sit on the segment. |
| draw.io swimlane child coordinates appeared offset | Children of a `swimlane` cell are positioned **relative to the swimlane's top-left including its title bar** (`startSize`, default 30). When converting absolute layouts to nested swimlanes, subtract the swimlane origin from each child's x/y and account for the header height. |
| Assuming `billing-service` is the Galaxion invoice source | `billing-service` is no longer used; target only `billing-api` for Billing. |
| Using `invoices/composed` as customer invoice detail | This is not the selected V1 path. Retrieve the PDF via `bill-run-documents`, then extract structured invoice JSON before the comparison engine. |
| ODP template slides stayed visually blank despite text in `content.xml` | Do not keep patching ODP placeholders blindly. Generate a PPTX with standard PowerPoint text shapes (e.g. via `python-pptx` in a temp venv) when no LibreOffice renderer is available. |
| Presentation content overflowed template frames | For `Presentation.odp`, prefer simple large layouts, one idea per slide, and two short bullets max; do not fill every placeholder just because it exists. |
| Treating Genesys as the AI brain | Keep Genesys as contact-center SoR only; RAG, billing rules, guardrails, memory and escalation content stay in the backend. |
| Validating only end-to-end voice latency | Measure each slice separately: channel ingress, end-of-turn, STT, backend, BSS/PDF, comparison, RAG, LLM, TTS, channel egress and Genesys handoff. |
| Reusing old implementation assumptions on the restart branch | Do not assume `backend/`, `frontend/`, `voice-agent/` or `docker-compose.yml` exist on `feat/restart-from-scratch`; rebuild from backlog and target architecture. |
| Broad patch on repeated Markdown status fields updated the wrong tickets | When changing backlog status, include the exact ticket header in patch context and reread the target section before committing. |
| `git diff --stat` hid new untracked scaffold files | Always pair diff review with `git status --short` and explicitly stage new folders such as `voice-agent/`. |
| STT scaffold emitted events but not metrics/logs | Runtime scaffolds must expose local OpenTelemetry-compatible evidence: events, metrics, structured logs, correlation id, provider, outcome and duration. |
| LLM repeated greetings despite "don't repeat" in system prompt | Conversation history was appended to the **user message** — LLM ignored it. Moving history into the **system message** + using "INTERDIT" phrasing fixed it for Mistral. |
| LLM never greeted on first message despite "greet if history is empty" | `buildHistory()` included the current user turn (just added via `addUserTurn()`), so history was never empty — even on the first message. Exclude the last turn (current question) from the history sent to the LLM. |
| `buildHistory()` double-counted the current question | The orchestrator calls `addUserTurn(question)` then `buildHistory()` which returns `lastTurns(N)` including the just-added turn. The question is already in the `user()` message — it should not also appear in the system history. Use `subList(0, size - 1)` to exclude it. |
| POST fallback sent `conversationId` (camelCase) but backend expects `conversation_id` | `ConversationController.AskRequest` uses `@JsonProperty("conversation_id")`. The Python bridge's `RAGBackendClient.ask()` was sending `"conversationId"` — backend silently fell back to `"default"`, splitting voice history. |
| Dead v1 voice pipeline (Deepgram STT, Piper TTS, WebSocket handlers) cluttered the codebase | The current architecture uses a Python bridge (Gradium STT/TTS) communicating with Java via REST/SSE only. Removed 504 lines of dead code: `DeepgramSttAdapter`, `PiperTtsAdapter`, `VoiceWebSocketHandler`, `TwilioMediaStreamHandler`, `VoiceController`, `VoiceConfig`, `WebSocketConfig`, `SpeechToTextPort`, `TextToSpeechPort`, and associated YAML config. |
| Domain-filtered vector search excluded legacy chunks with no `domain` metadata | `PgVectorStoreAdapter` stored chunks without `domain` when the param was null. Fix: always store `domain` metadata (default to `"general"`), and search filter uses `OR(domain=agent, domain=general)` to include shared knowledge. |
| `IntentClassifier` picked arbitrary agent on keyword tie | Two agents scoring equally → winner depended on iteration order. Fixed by preferring the current session agent (stickiness) when scores tie. |
| Short keyword `ip` matched via `contains()` → false positives on "équipement", "équipe" | Switched from `String.contains()` to word-boundary matching (`isWholeWordMatch()` checking adjacent characters are not alphanumeric). |
| `setState` called during render in `VoiceChat.tsx` (audio state sync) | `if (audioState === 'playing') setVoiceState('speaking')` was in the component body. Moved to `useEffect` with `[audioState, voiceState, vadActive]` dependencies. |
| `useAudioQueue.clear()` didn't stop current `AudioBufferSourceNode` | `clear()` emptied the queue and reset flags but never called `source.stop()`. Audio kept playing on WebSocket errors. Now mirrors `flush()` behavior. |
| Gradium STT fixtures were ASCII `.txt` placeholders renamed `.wav` (19–33 bytes) — no real engine could transcribe them | Generate real audio with macOS `say -v <voice> -o x.wav --data-format=LEI16@16000 --file-format=WAVE`, then strip the WAV header to **raw PCM16** via Python `wave.readframes()`. Gradium wants raw PCM (`input_format=pcm_16000`, `Content-Type: audio/pcm`), NOT a WAV container — a 44-byte header sent as samples causes a leading click. Store fixtures as `.pcm`; `FixtureSttProvider` still resolves the sidecar via `audio_path.with_suffix(".txt")`. |
| Live STT quality gate reported real transcripts as "failed" (WER 1.0 for `Bonjour` vs `Bonjour.`) | `word_error_rate` compared raw whitespace-split tokens with no normalization: punctuation, case and accents (`telephone` vs `téléphone`) all count as errors. Normalize both reference and hypothesis (lowercase, strip punctuation, fold accents) before scoring. The gate is unusable against a real engine otherwise (RF-008 / TASK-STT-011). |
| Batch STT latency looked like a fixed cost but scales with audio length | Gradium processes the whole clip after upload: ~1.1 s for 1 s silence, ~2.3 s for 3.4 s, ~2.7 s for 4.3 s. Streaming/partial transcription (TASK-STT-010) is the real latency lever, not tuning the batch call. |
| US-036 pipeline timing report could hide un-instrumented slices | `PipelineTimingReport` always emits all six canonical journey slices in flow order; slices with no span are reported `"measured": false` + a reason/ticket, never omitted — a missing measurement must not look like a fast one. Per slice, the first present candidate span name wins so a web run (`web.voice.ingress`) and a fixture run (`stt.audio.accept`) never mix into one distribution. |
| Failure sanitization only redacted path-separated tokens | `_redact_token` now also redacts bare filenames (`<redacted-file>`) and identifier-like tokens (`<redacted-id>`: UUID, secret prefixes, ≥7-digit runs, mixed ids); a `_SAFE_TOKENS` allowlist keeps technical tokens (`pcm_16000`, `audio/pcm`) readable. Words/dates preserved; `error_code` + 160-char cap kept (TASK-STT-005 / RF-009). |
