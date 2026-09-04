# Repository context for Claude (and similar assistants)

**Voice Support Bot** — V2V (voice-to-voice) RAG voice agent for Telecom/ISP support.

> This repository (`voice-support-bot`) is a **separate git repository** (default branch `main`) nested in the `BMad` workspace. Bot commits belong here, not in the `BMad` repository.

> Self-contained guidance: when working in this repo, use **only** this repository's `CLAUDE.md` / `AGENTS.md` and the skills under `voice-support-bot/.cursor/skills/`. Do **not** apply the workspace-root `BMad/claude.md`, `BMad/agents.md`, or root `.cursor/skills/` (those govern `cursor-usage-dashboard/`).

> Branch note: `feat/restart-from-scratch` began by removing the previous stack
> (preserved on `main` as backup/reference), then **rebuilt from scratch**. Through
> **Sprint 9** the branch now runs a two-service stack: the Python voice runtime
> (`voice-agent/` — STT/TTS, batch + streaming WebRTC, barge-in) and a rebuilt Java
> conversation backend (`backend/` — RAG over pgvector, guardrails, confidence,
> memory), plus a minimal `docker-compose.yml` (Postgres + Ollama). Only the
> standalone React `frontend/` and the legacy `agent/bot.py` / `bridge_server.py`
> remain un-rebuilt (the web client is the `web_voice/` static page). Through **Sprint 13**
> the **Genesys Audio Connector** is built + deployed to the pilot (`v0.8.0`,
> `VOICE_GENESYS=on`, endpoint `GET /genesys/audiohook` on the ADR-0047 `:8090`; app-layer
> Step 0b self-test PASSED) with by-reference escalation handoff — but the **live-org** legs
> (real Genesys tenant reachability/TLS trust, native barge-in/EOT, Architect fail-safe) and
> **degraded modes** (TASK-WEB-044) are still pending. Still target-only: billing/BSS,
> invoice comparison, and telephony (live-org Genesys still to prove).

> Delivery rule: no development starts without a ticket. Branching uses a **two-level
> model** (decision 2026-07-29): one sprint branch `feat/sprint-NN-short-theme` per sprint,
> created from `feat/restart-from-scratch`, and each user story / bug / technical task on its
> own ticket branch (`us/US-XXX-short-name`, `fix/BUG-XXX-short-name`,
> `task/TASK-XXX-short-name`) created **off the current sprint branch**. A merge-ready ticket
> branch merges into its sprint branch (`git merge --no-ff`); the sprint branch merges into
> `feat/restart-from-scratch` only at sprint closure. The user is the final validator; do not
> merge any branch — ticket or sprint — unless the user explicitly asks for the merge.
> When the user says a ticket is validated, record the validation, rerun checks,
> then commit and push the ticket branch automatically. Merge still requires an
> explicit user request. Full model + diagram: `docs/operations/development-workflow.md`.

## Application layout

| Part | Path | Stack |
|------|------|-------|
| Product backlog | `product-backlog/` | V1 epics, user stories, decisions, open questions |
| Architecture docs | `docs/architecture/` | ADRs, architecture spine, diagrams, reviews |
| Product docs | `docs/product/` | V1 scope and broader functional specification |
| Integration docs | `docs/integrations/` | Galaxion/BSS contracts and missing inputs |
| Knowledge base | `knowledge-base/` | Billing/support/commercial content for future RAG |

Both `voice-agent/` (Python voice runtime, port 8090) and `backend/` (Java Spring
Boot conversation engine, port 8080) are **rebuilt from scratch on this branch** and
are runnable (full web Voice2Voice loop with RAG, streaming + barge-in, through
Sprint 9), together with a minimal `docker-compose.yml` (Postgres + Ollama). The
rebuilt backend's API differs from the legacy `main` one (`/api/conversation/converse`,
`/converse-stream`, `/answer`, `/retrieve`; no `/ask`, `/ask-stream`, `/seed`). Not
present on this branch: the standalone React `frontend/` and the legacy `agent/bot.py`
/ `bridge_server.py` (those live on `main`).

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
- Storage: **one Postgres database** (`pgvector/pgvector` image, port 5433). The schema is owned by **Liquibase** (TASK-INFRA-009, ADR-0041), not Hibernate `ddl-auto` / Spring AI `initialize-schema` (both now off): the backend runs the **app changelog** at startup (`db/changelog/db.changelog-master.yaml`, as the app user) to create `vector_store` (Spring AI 1.0.0's exact DDL — `metadata json`, Spring AI query-casts to `jsonb`; `embedding vector(768)`; `spring_ai_vector_index` HNSW cosine) + `kb_source_state`. The privileged **bootstrap changelog** (`db/changelog/bootstrap/`, `CREATE EXTENSION vector`/`uuid-ossp` + grants) runs once as superuser at deploy Step 4 (one-shot `podman run liquibase`); only `CREATE DATABASE`/`ROLE`/`ALTER … OWNER` stay a psql pre-step. Local dev creates the extensions via `scripts/dev-db-init/` (mounted in `docker-compose.yml`).
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
- Actual backend answer routes are `POST /api/conversation/{converse,converse-stream,answer,retrieve,warm-up}` (not `/ask*`). `converse-stream` is the guarded SSE (`chunk` = one vetted sentence, `done` = `{text, confidence?, grounded}`, `error` = `ErrorResponse`). `warm-up` (TASK-BE-017) is body-less, always 200, api-key gated.
- The `domain` (support|billing|commercial) tags each chunk; search filters `domain == X OR general`. Markdown front-matter must match the historical domains (telecom -> support, billing -> billing, commercial -> commercial) to preserve behavior.
- **Voice path is intentionally cross-domain (BUG-007):** `/converse` + `/converse-stream` pass `domain=null` to grounding, so retrieval spans **all** domains (audience fail-closed still applies). This is by design — there is **no runtime classifier of the incoming question** (ADR-0015 not implemented). The `DomainClassifierPort` (ADR-0030) tags KB articles by domain at **ingestion**, not the runtime query, so no reliable per-question domain can be supplied; forcing one would need a query router and could drop relevant chunks. Per-domain scoping stays on `/answer` + `/retrieve` (caller-supplied domain). Two regression tests (`ConversationServiceTest` / `StreamingConversationServiceTest` `retrieves_across_all_domains_by_design`) lock the null-domain contract. The cross-domain retrieval-precision trade-off is tracked in **OQ-008**. Revisit only when a runtime query classifier lands.
- Galaxion Billing V1: use `billing-api`, not `billing-service` (no longer used). Invoice retrieval goes through `GET /bill-run-documents/search`, then `GET /bill-run-documents/{document_id}/download`.
- No identified Galaxion endpoint provides structured invoice lines for V1; invoice detail must come from the PDF through a deterministic `InvoicePdfExtractor` before comparison.
- Local full-stack run: `VOICE_BACKEND_URL` is the backend **server base** URL (`http://host:8080`); the bridge appends `/api/conversation/converse` and derives the `converse-stream` / `warm-up` siblings itself (`conversation_backend/backend_factory.py`, BUG-013). A legacy **full** converse URL is still accepted (idempotent, not doubled). The WebRTC test page is served at `http://127.0.0.1:8090/webrtc.html` (`/` → `index.html`). The backend api-key gate is open when `CONVERSATION_API_KEY` is empty; source `GRADIUM_*` / `MISTRAL_*` from the repo-root `.env` (`set -a; . ../.env; set +a`).
- Centralized observability (TASK-OPS-007) is **opt-in via one variable**: Ansible `otel_collector_endpoint` (empty ⇒ export OFF on both tiers). The optional collector+Prometheus stack lives in `deploy/observability/docker-compose.otel.yml` (Prometheus scrapes the collector's `:8889` exporter, UI on `:9090`). Backend template gates both `OTEL_METRICS_EXPORT_ENABLED` and `OTEL_TRACES_SAMPLER_ARG` off when the endpoint is unset.

## Testing commands

The runnable code on `feat/restart-from-scratch` is the Python voice runtime under
`voice-agent/`. Run its tests through the venv (the full suite needs `pipecat-ai` +
`behave`; a bare system `python3` fails with `ModuleNotFoundError: No module named
'pipecat'`). For documentation-only changes, `git diff --check` is enough.

```bash
cd voice-agent
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt   # first time
./.venv/bin/python -m unittest discover tests   # 502 tests
./.venv/bin/behave                              # 13 features / 36 scenarios / 169 steps
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
| `voice-agent` tests error with `ModuleNotFoundError: No module named 'pipecat'` | The full suite (since Sprint 4) needs `pipecat-ai` + `behave`, which live in `voice-agent/.venv`, not the system `python3`. Run tests via the venv: `python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`, then `./.venv/bin/python -m unittest discover tests` (502 tests) and `./.venv/bin/behave` (13 features/36 scenarios/169 steps). System `python3` only sees stdlib-only tests and silently reports fewer tests + pipecat import errors. |
| WebRTC energy-based end-of-turn never fired on a file-based test clip (empty US-036 telemetry despite `received_bot_audio: True`) | **Opus DTX**: pure digital silence sends *no* RTP packets, so the trailing-silence aggregator never sees silence frames and never flushes; `received_bot_audio` is just the bot output track's silence keepalive, not a real answer. A real mic emits an ambient noise floor so packets keep flowing. Fix for file-based WebRTC clips: pad the tail with **low-amplitude noise** (peak ≪ speech threshold ~1000), never zeros. Also don't gate a headless client's hangup on "first bot frame" (keepalive fires instantly) — hold the call open a fixed window (`--hold`). TASK-WEB-007. |
| `SmallWebRTCRequestHandler` / signaling drags in FastAPI; `SmallWebRTCTransport` pulls `opencv-python` | The bundled request handler imports `fastapi`; our stdlib `http.server` avoids it by driving `SmallWebRTCConnection` directly (`initialize` → `get_answer`) in `web_voice/webrtc_signaling.py`. The transport hard-imports `cv2` even for audio-only (via `av`+opencv, which also clash on a duplicate `libavdevice` dylib → benign macOS `objc[...]` warning). Keep both behind the import guard (`webrtc_support.py`); consider `opencv-python-headless` for the image (ADR-0022). Threaded stdlib server + streaming pipeline need one persistent asyncio loop (`web_voice/async_loop.py`); the HTTP handler submits coroutines with `run_coroutine_threadsafe`. |
| Assuming Silero VAD is natively auto-wired into a Pipecat pipeline | In **pipecat 1.5.0** there is **no** `vad_analyzer` field on `TransportParams` and no `VADAnalyzer` consumer in the transports. `SileroVADAnalyzer` (`pipecat.audio.vad.silero`) exists only as a standalone `analyze_audio(pcm) -> VADState` component you must drive by hand — the *same* integration effort as the energy `StreamingEndOfTurnDetector`. Keep the existing detector for onset; Silero is a drop-in **verdict** upgrade (needs `onnxruntime`), not free native wiring (ADR-0025, TASK-WEB-008). |
| Barge-in interruption is native in Pipecat (don't build a bespoke flush/cancel) | `InterruptionFrame` is a `SystemFrame` handled out-of-band: a `FrameProcessor` **cancels & re-creates its process task** (an in-flight streaming synthesis gets `asyncio.CancelledError`) and the base **output** transport flushes its audio buffer + stops playback. Call `broadcast_interruption()` to send it up+downstream. The output transport also emits `BotStartedSpeakingFrame`/`BotStoppedSpeakingFrame` **both directions**, so an upstream processor gates barge-in on bot-speaking state for free (TASK-WEB-008). |
| Interruptible streaming synthesis leaked the WebSocket on barge-in | `asyncio.CancelledError` is a `BaseException`, so `except Exception` does not catch it — the session was never closed on interruption. Wrap the stream in `try/except asyncio.CancelledError` (emit an `interrupted` outcome, re-raise) **plus** a `finally` best-effort `aclose()`; under a re-cancellation during close the socket may be dropped rather than cleanly closed. |
| Interrupted TTS turn skewed the `tts_first_audio` p95 | `voice_common/pipeline_timing.py` groups spans by name with **no outcome filter**, so an interrupted `voice.tts.first_audio` span carrying *total-elapsed* polluted the distribution. Emit that span with the real time-to-first-audio and **only if audio actually played**; put elapsed on the `tts.interrupted` event instead (TASK-WEB-008 review). |
| Barge-in self-interrupted without headphones (browser echo cancellation not enough) | Live-only bug: `getUserMedia({echoCancellation:true})` attenuates but does not remove the bot's speaker→mic echo, and an energy VAD reads the residual as speech → the bot cuts itself. The echo is *continuous*, so N-frame confirmation alone can't reject it — the discriminating lever is **amplitude** (residual echo after AEC sits below direct voice). Gate the barge-in *cut* on a raised **barge-in amplitude threshold** (above the STT onset threshold) **plus** an N-frame sustained-onset confirmation (rejects spikes); keep opening the STT session on normal onset so the utterance is still captured. Make both env-tunable (`VOICE_BARGE_IN_THRESHOLD`/`VOICE_BARGE_IN_FRAMES`) — echo levels are setup-specific, so a code-baked threshold can't be right for every machine (TASK-WEB-008, ADR-0025 point 7). |
| Wanting app-startup Liquibase to `CREATE DATABASE` / `CREATE ROLE` / `CREATE EXTENSION` | Liquibase connects **into** a DB **as the login role**, so three ops can never be app-startup (TASK-INFRA-009, ADR-0041): `CREATE DATABASE` (can't create the DB it connects to; non-transactional), `CREATE ROLE …LOGIN` (the app connects **as** it → must pre-exist), `CREATE EXTENSION vector`/`uuid-ossp` (superuser-only; the pilot app role isn't superuser). Split: app changelog (tables) at startup as app user; a **superuser bootstrap changelog** (extensions/grants) run once via a one-shot `podman run liquibase` container with its **own** tracking tables; only DB/role/`ALTER … OWNER` stay a psql pre-step. |
| Liquibase `vector_store` DDL drifting from Spring AI → RAG breaks | The Liquibase app changelog must reproduce Spring AI 1.0.0's PgVectorStore schema **byte-for-byte** (extracted from `spring-ai-pgvector-store-1.0.0.jar` via `javap -c`): `id uuid DEFAULT uuid_generate_v4() PRIMARY KEY, content text, metadata json` (**json, NOT jsonb** — Spring AI query-casts to jsonb), `embedding vector(768)`, index `spring_ai_vector_index USING hnsw (embedding vector_cosine_ops)`. Guard the changeset with `preConditions … not tableExists / onFail: MARK_RAN` so it's a no-op on a legacy dev DB already created by `initialize-schema`. Set `ddl-auto: none` + `initialize-schema: false`; keep a schema-parity test. |
| Adding `liquibase-core` broke `commons-csv` (`NoClassDefFound …UnsynchronizedBufferedReader`) | liquibase-core 4.29.2 pulls `commons-io 2.16.1`; commons-csv 1.14.1 needs **≥ 2.17** (that class). Maven mediation picked 2.16.1 (Spring Boot 3.4.1 BOM does NOT manage commons-io). Fix: pin `commons-io` to **2.19.0** in `dependencyManagement` (backward-compatible, satisfies both). Adding a dep can silently *downgrade* a transitive of another dep — always re-run `mvn test` and `mvn dependency:tree -Dverbose` after. |
| Where the pgvector `vector`/`uuid-ossp` extensions come from once Spring AI `initialize-schema` is off | Pilot: the superuser **bootstrap changelog** (Step 4b). Local dev: `scripts/dev-db-init/01-extensions.sql` mounted at `/docker-entrypoint-initdb.d/` in `docker-compose.yml` (runs once on empty volume). The dev pgvector image's `voicesupport` user is a **superuser** (that's why `initialize-schema` worked in dev but fails on the unprivileged pilot role). |
| Voice→backend spans landed in **separate traces**; no live OTel context during the HTTP call | The voice runtime records telemetry and exports **post-hoc** (after the turn), so there is no ambient span to propagate. Fix (TASK-OPS-007): derive a **deterministic** W3C `traceparent` from the `correlation_id` (pure BLAKE2b → 128-bit trace + 64-bit span, `voice_common/trace_context.py`), inject it on the backend HTTP hop, and at export time start the `voice.turn` root **under that same derived context**. Backend continues the trace via `micrometer-tracing-bridge-otel` (default W3C propagation + **ParentBased** sampler — the `01` sampled flag survives a low probability arg). Same ids on both tiers, no shared runtime state. |
| Exported voice child spans got **independent trace ids** | `otel_export.py` started children with `tracer.start_span(name)` and **no context** → each became its own root/trace. Parent them: capture `root_ctx = set_span_in_context(root)` and pass `context=root_ctx` to every child so the turn forms one span tree. |
| Changing the end-of-turn runtime hold by editing the detector's `DEFAULT_SILENCE_WINDOW_MS` | Wrong lever. The **streaming runtime** default is resolved in `web_voice/webrtc_signaling.py::_silence_window_config()` (now returns `{"silence_window_ms": 350.0}` via `PILOT_END_OF_TURN_SILENCE_MS`). The detector library constant stays **500 ms** for batch/fixture callers. Returning `{}` means "use the library default"; return the value explicitly to change only the streaming path (TASK-WEB-022). |
| Flipping `VOICE_BACKEND_STREAM` code default ON felt risky for stub/fake backends | Safe: `_stream_this_turn()` only takes the streaming path when the backend actually exposes `answer_stream`. Stubs/fakes without it transparently keep the blocking path, so the default flip broke no tests (TASK-WEB-022). Env parsing was also inverted to fail-safe (`not in ("0","false","no","off")`). |
| Ending a call on the first customer closing word ("au revoir") felt abrupt / risked false positives | End-of-call needs a **confirmation turn**, not an immediate cut (US-041, ADR-0035). `CallEndFarewellProcessor` (on a new `pre_answer` seam between STT and answer) suppresses the answer on a closing, speaks "Souhaitez-vous autre chose ?", then ends only on a done-confirmation OR a bounded confirmation-scoped silence timeout. Keep detection **deterministic/no-LLM**: accent-insensitive word-boundary token matching with negation + embedded-request guards (`ClosingIntentDetector`), env-tunable phrase sets (`VOICE_FAREWELL_*`). |
| Confirmation turn treated a repeated goodbye ("non, au revoir") as a new request → call never ended | The confirmation handler only checked `is_done_confirmation(text)`; a customer re-saying a standalone closing fell through to the "answer normally" branch. Fix: in the confirmation turn, `_confirms_done` also ends the call when `detect_closing(text).is_closing` — a repeated closing is a done-confirmation, not a fresh request (adversarial-review finding). |
| End-of-call teardown risked duplicating shutdown logic | Do not write a bespoke close path. `CallEndFarewellProcessor` delegates ending to an injected `end_call(signal)` callback (stays transport-agnostic + unit-testable); the WebRTC signaling wires it to the existing **TASK-WEB-008 `drain()`** path so the closing audio is drained before the session ends, and records the `voice.call_end` reason (`customer_farewell` vs `client_stop`/`client_drop`). |
| `SleepFrame` import path guessed as `pipecat.frames.frames` | In pipecat 1.5.0 `SleepFrame` (and `run_test`) live in **`pipecat.tests.utils`**, not `pipecat.frames.frames`. Use `from pipecat.tests.utils import SleepFrame, run_test` to drive time-based FrameProcessor tests (e.g. confirmation silence timeout). |
| FrameProcessor unit test built a fake telemetry with `SimpleNamespace` → `.record()` AttributeError | The processor calls `telemetry.record(name, correlation_id=..., **attrs)`. A `SimpleNamespace` has no `record`. Use the real `voice_common.telemetry.TelemetryRecorder` in tests (it exposes `.record()` and lets you assert emitted events). |
| Farewell/backend test envelope missing `conversation_id`/`language` → backend request build failed | The answer stage builds a backend request from the turn envelope. A partial fake (only `correlation_id`) breaks it. Give test/Behave envelopes the full set: `correlation_id`, `conversation_id`, `channel`, `language`. |
| Assuming latency lever 1 (backend-stream-to-TTS) needs a new backend "vetted-only" contract | `POST /api/conversation/converse-stream` (SSE, ADR-0013) **already** emits guardrail-vetted sentences one at a time: `GuardedSentenceEmitter` grounds first, runs `OutputGuardrail.check` on **each sentence before emitting it**, stops the stream + emits the safe hand-off if blocked. DEC-002 is enforced backend-side; the runtime just consumes the existing stream (no backend change for safety). Lock it with a **service-level incremental-delivery** test (first vetted sentence reaches the consumer before the full answer completes) — the emitter/service already cover no-chunk-before-vetting + blocked→hand-off. |
| Warm-up path accidentally polluting conversation memory or blocking the first turn on a cold provider | `WarmUpService` (TASK-BE-017) exercises embedding (`KnowledgeRetrievalPort.retrieve`) + LLM (`AnswerGeneratorPort.generate`) once and must: take **no `ConversationMemoryPort`** (structurally side-effect-free), discard the output, be repeatable, and **never throw** — a failed step is recorded as a warm-up miss (`recordLatency(..., "error", ...)`) so the runtime treats it best-effort. `POST /api/conversation/warm-up` always returns 200 with per-model flags; api-key gated via `WebSecurityMvcConfig` path list. |
| `rg -r` / `rg -rl "pattern"` mangled file content in output (e.g. `converse-stream` printed as `l`) | `-r` is ripgrep's **replace** flag, not "recursive" — `-rl` parses as `-r l` (replace matches with `l`) and prints content mode. There is no `-r` for recursion (rg recurses by default). Use `rg -l` for files-with-matches; never pass `-r` unless you mean replacement. |
| Believing `backend/` is absent because CLAUDE.md says it was removed on `feat/restart-from-scratch` | The Sprint 7 answer engine **rebuilt** the Java backend; it exists on the sprint/ticket branches (e.g. `feat/sprint-10-pilot-latency`) with the full `com.voicesupport.conversation` module (`converse`, `converse-stream`, `answer`, `retrieve`, `warm-up`). The "removed" note describes the initial restart state only. |
| Batch `/api/voice/turn` spoke only the **last** sentence of a multi-sentence answer (BUG-015) | With `VOICE_BACKEND_STREAM` on (default since TASK-WEB-022) the backend emits **one `TextFrame` per vetted sentence**, so the batch pipeline synthesizes several `TTSAudioRawFrame`s. `_AudioCaptureSink` accumulates them all into `BatchTurnResult.audio`, but `TtsFrameProcessor.response` (hence `tts_response`) is **overwritten per frame** → holds only the last sentence. The root UI (`/` → `index.html`) posts to `/api/voice/turn`, and `_handle_turn` sent `tts_response.wav` (last) instead of `result.audio` (all). Fix: wrap the accumulated PCM once (`_full_turn_response` → `pcm_to_wav(result.audio, …)`) for both the WAV sent and the `record_egress` byte count; fall back to the last synthesis when the sink is empty. WebRTC (`webrtc.html`) is unaffected (each sentence's frame goes straight to the transport track). Interim mitigation without a rebuild: `VOICE_BACKEND_STREAM=0`. |
| Ansible voice deploy aborts at "Wait for voice HTTP health" though the bridge is up (recurring) | The health gate probes `http://127.0.0.1:8090/` (`group_vars/voice.yml health_url`). On the pilot Podman hosts the published port answers on `0.0.0.0:8090` and via the **host LAN IP** (`curl http://<host-ip>:8090/` → `200`, container `healthy`), but **host→loopback** returns `000` — a port-forwarder quirk, not an app failure. With `retries:30 delay:5` + `serial:1 max_fail_percentage:0`, the false-negative burns ~150s then aborts the whole play **after** the node is already recreated at the new tag, and never reaches the next node. Confirm health out-of-band (`ssh <host> 'curl http://$(hostname -I|awk "{print \$1}"):8090/'` + `docker inspect --format {{.State.Health.Status}}`). To finish a blocked node manually: bump `IMAGE_TAG` in `/opt/voice-support/voice/.env` (preserves the vault-rendered secrets — never hand-write them) then `sudo bash -c 'cd /opt/voice-support/voice && IMAGE_TAG=<tag> podman compose pull && podman compose up -d --remove-orphans'`. Proper fix (follow-up, ticketed TASK-INFRA-011): point `health_url` at the host IP or a `podman inspect …Health.Status` probe. Same podman host→loopback quirk also breaks a `ws://127.0.0.1:8091` SSH-tunnel handshake — tunnel to the bridge **LAN IP** instead (TASK-WEB-039). |
| `streaming_latency_report.py` reported "all six canonical per-slice NOT MEASURED" for the WebSocket path | Stale/incorrect observation. On a re-run the WS per-slice table populates fine (`end_of_turn`/`stt`/`backend_first_token`/`tts_first_audio`/`channel_egress` all `measured=true`); the **only** unmeasured slice is `channel_ingress` because the headless client emits no browser-mic ingress span (→ TASK-WEB-040). Re-run the tool and inspect the JSON before ticketing a mapping gap — don't ticket off a remembered/summary claim. |
| Framed `stt.time_to_first_partial` (~1.4–2.2 s) as the ADR-0029 mouth-to-ear bottleneck | Wrong slice. `time_to_first_partial` happens **while the caller is still speaking** (pre-EOT), so it is NOT on the post-EOT mouth-to-ear path. The dominant post-EOT STT slice is `time_to_final` (finalize tail, p95 ~1235 ms on the v0.6.0 pilot WS sample). The composite `time_to_first_audio` uses `stt = time_to_final`, then `backend_first_token`, then `tts_first_audio`. Levers: TASK-STT-014 (STT tail) + TASK-BE-020/BE-033 (backend). |
| Assuming a single-port async voice server (ADR-0047) needs a new heavy framework | `aiohttp` is **already installed transitively** (via `pipecat-ai`/`aiortc`; 3.14.1 on Python 3.14) — its core deps (aiohappyeyeballs/aiosignal/attrs/frozenlist/multidict/propcache/yarl) are all already present, so adopting it for the one-port HTTP+WS server adds **zero new wheels**. FastAPI would add starlette+pydantic(+Rust core)+uvicorn for no benefit. Spike proved static + `/api/voice/*` + WS `101` upgrade on one aiohttp app (`voice-agent/spikes/aiohttp_one_port/`, `verify.py` PASS). Verdict: aiohttp for TASK-WEB-038. |
| Verifying a one-port aiohttp app by hand-binding a port | Use `aiohttp.test_utils.TestServer(make_app())` + `aiohttp.ClientSession` — it binds an ephemeral port and gives `make_url()`; `session.ws_connect(...)` drives the WS upgrade. No fixed port, no manual server lifecycle. |
| **FIXED (TASK-INFRA-011)** the recurring voice-deploy health-gate hang above | The proper follow-up is now implemented: `roles/compose_tier/tasks/health.yml` polls the **container's own health verdict** (`docker inspect --format {{.State.Health.Status}} <name>` until `healthy`, 30×5s) when `health_container_name` is set — the container `HEALTHCHECK` curls `localhost:8090` **inside the container namespace**, so it is immune to the host loopback/firewall/port-forwarder quirk. `group_vars/voice.yml` sets `health_container_name: voice-support-bridge`; the HTTP `uri` probe is kept as the **fallback** (runs only when `health_container_name` is unset, e.g. backend loopback `:8080` which works), so the QA contract (`ansible.builtin.uri` present) holds. Both probes are mutually gated: `when: health_container_name \| length > 0` vs `when: health_url \| length > 0 and health_container_name \| length == 0`. Escape the Go template in the Ansible `command` with `{% raw %}…{% endraw %}` so Ansible does not try to template `{{.State.Health.Status}}`. No more per-host `-e health_url=<service-IP>` workaround. |
| A subagent reported as "error"/"failed" may have actually **completed** (even committed + pushed) before its turn died | Never blindly redo a "failed" subagent's work — inspect the **real repo state** first (`git log`, `git status -sb`, ahead/behind vs origin). Worse, a still-active/zombie worker can land a commit **concurrently** while you inspect (observed: HEAD moved from one commit to the revert commit between two status checks). Verify deterministically by content; don't trust the status label. |
| Surgically removing one feature's changes when a `git revert -m 1 <merge>` conflicts with later commits that touched the same docs | If the target files' **only** changes since a base commit are that feature's, use `git checkout <base> -- <files>` (deterministic reverse-apply) instead of `git revert`. It sidesteps the merge-revert conflicts with unrelated later edits to the same files. |
| A branch assumed to be "the active sprint" was actually **closed + released** | `feat/sprint-12-external-voice-websocket` was closed (merge `0a10da4`) and tagged `v0.6.0`, while mainline `feat/restart-from-scratch` had already advanced to `v0.7.0`; a week of work got layered on the *closed* branch, diverging from mainline. Before treating a branch as active, verify: `git tag`, the closure merge, `git merge-base <branch> <mainline>` (here it equalled the v0.6.0 commit), and ahead/behind vs mainline. |
| Forward-porting a diverged branch's tail onto mainline | Cherry-pick **per ticket** onto a fresh branch off mainline (NOT a wholesale merge, NOT `rebase --onto`); drop net-zero add+revert pairs and merge commits; resolve shared-ledger conflicts (backlog-index, done-tasks, CLAUDE/AGENTS, ADR README) by **union**. Caveat: `git cherry <mainline> <branch>` marks commits `+` (not-equivalent) even when their content is already on mainline, because the union conflict-resolution changed the patch-id — a `+` is **not** proof a commit is unique; confirm by content/grep. |
| `git branch -d` refused to delete a superseded sprint/ticket branch (not merged) | `-d` is a safety net that refuses non-merged branches. For a branch whose content is preserved elsewhere (forward-ported, or a release tag), delete with `-D` **and explicit user approval**. Deleting a *released* sprint branch is safe because the release is preserved by its tag + the closure merge already in mainline. |
