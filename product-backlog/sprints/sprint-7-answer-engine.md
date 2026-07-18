# Sprint 7 — Real Conversation Answer Engine (RAG over the knowledge base, EPIC-005)

## Sprint Objective

Turn the Voice2Voice loop's **stub** answer into a **real, evidence-grounded
answer engine**. Sprints 1–6 built the full streaming voice pipe (STT → answer →
TTS over WebRTC), but the "answer" is still a deterministic placeholder: the bot
does not yet explain anything. This sprint builds the Java backend behind the
existing conversation contract (ADR-0021) so the bot answers **generic billing /
telecom / commercial questions grounded in the `knowledge-base/`** via RAG, with
guardrails before and after retrieval, a provider-agnostic LLM wording step, and
full per-slice observability.

This is the **product-value** sprint: it proves the bot can say something true and
useful. It is deliberately scoped to **knowledge-base-grounded answers**, not
customer-specific invoice amounts — the customer identity / BSS / PDF / comparison
chain stays gated by its open questions (see Out Of Scope).

## Status

**Status:** Planned — **not started.** Preparation only. This sprint must not start
until **Sprint 6 is finished and validated** (see Entry Condition).
**Created:** 2026-07-17
**Predecessor:** [`sprint-6-streaming.md`](sprint-6-streaming.md) (Sprint 6 — ✅ Done,
closed 2026-07-17; ADR-0018 latency gate MET via TASK-STT-013, `time_to_first_audio`
p95 761.5 ms < 800 ms)
**Working branch:** `feat/sprint-7-answer-engine` (to be cut from
`feat/restart-from-scratch` once Sprint 6 is merged/validated)
**Final validator:** User
**Merge rule:** no branch is merged unless the user explicitly asks.

## Entry Condition (hard gate before this sprint starts)

- **Sprint 6 closed and validated:** `time_to_first_audio` p95 < 800 ms met
  (TASK-STT-013 done) **or** the criterion explicitly revised by
  Product/Architecture (OQ-005). Finishing Sprint 6 closes the latency ticket by
  construction; it is **not** a Sprint 7 ticket.
- Rationale: adding a real (slower than stub) backend on top of an unresolved STT
  finalize tail would make the end-to-end latency unattributable. A clean latency
  baseline must exist first so the backend's own cost can be measured in isolation.

## Roadmap Context

| Sprint | Theme | State |
|---|---|---|
| Sprint 1–4 | STT validation → hardening → TTS → Pipecat batch | ✅ Done |
| Sprint 5 | Backend answer bridge (stub/http contract, US-019 close) | ✅ Done |
| Sprint 6 | Streaming voice loop + latency (WebRTC/streaming/barge-in) | ✅ Done (closed 2026-07-17) — ADR-0018 gate MET (p95 761.5 ms) via TASK-STT-013 |
| **Sprint 7** | **Real answer engine — RAG over the knowledge base (EPIC-005) — this sprint** | 📋 Planned (prep only; gated on Sprint 6 close) |
| Sprint 8 (tentative) | Customer identity + BSS/PDF evidence + deterministic comparison (EPIC-002/003/004) → customer-specific invoice explanation | Planned — gated by OQ-001/003/004 |
| Sprint 9 (tentative) | Telephony channel (US-018) + Genesys advisor handoff (EPIC-007) | Planned — gated by OQ-006 |

## Why now (state that justifies the sprint)

- The voice pipe is complete and instrumented, but `--backend stub` returns a
  fixed, digit-free placeholder (ADR-0021). The product's reason to exist —
  explaining bills — is not demonstrated.
- The `knowledge-base/` already contains real FR content
  (`billing-faq.md`, `telecom-faq.md`, `commercial-faq.md`) with `domain`
  front-matter, ready for RAG ingestion.
- The conversation contract is already defined and stable (ADR-0021): request
  `{transcript, conversation_id, correlation_id, channel}` → response
  `{text|answer, confidence?}`. Sprint 7 implements the **server side** of that
  contract; the voice runtime and telemetry do not need to change.
- **OQ-007** (backend AI/RAG framework) was deferred and is now the first blocker
  to lift — nothing real can be built until it is decided.

## Prerequisite Decision (first ticket)

The backend AI/RAG framework (**OQ-007**) must be decided before any engine code.
It is **TASK-BE-001** below and blocks every other Sprint 7 ticket.

## Backend Architecture (decided — ADR-0026 + ADR-0027)

The internal structure is fixed before coding so TASK-BE-002 scaffolds the final
shape. Framework: **Spring Boot + Spring AI** ([ADR-0026](../../docs/architecture/adrs/ADR-0026-backend-runtime-and-ai-framework.md)).
Decomposition: **Hive-light modular monolith, two context-first bounded contexts**
([ADR-0027](../../docs/architecture/adrs/ADR-0027-backend-modular-decomposition-knowledge-conversation.md)),
following the `software-architect` skill's Layout B (package-by-context first).

```text
com.voicesupport
├── VoiceSupportApplication                 # Spring Boot bootstrap (root)
│
├── knowledge/                              # BOUNDED CONTEXT — ingestion + retrieval (full hexagon)
│   ├── domain/
│   │   ├── model/entity/                   SourceDocument, KbSourceState
│   │   ├── model/valueobject/              Chunk, Domain, ContentHash, Language
│   │   ├── service/                        KnowledgeSyncService, RetrievalService, TextChunker
│   │   ├── port/in/                        SyncKnowledgeUseCase, KnowledgeRetrievalUseCase  ← published API
│   │   ├── port/out/                       KnowledgeSourceConnector, VectorStorePort, EmbeddingPort, KbSourceStatePort
│   │   └── exception/
│   ├── application/service/                KnowledgeSyncAppService
│   └── infrastructure/
│       ├── adapter/in/rest/                KnowledgeController (+ dto/)
│       ├── adapter/out/pgvector/           PgVectorStoreAdapter
│       ├── adapter/out/embedding/          OllamaEmbeddingAdapter
│       ├── adapter/out/markdown/           MarkdownFolderConnector
│       ├── adapter/out/persistence/        JpaKbSourceStateAdapter
│       └── config/                         KnowledgeConfig (@Bean wiring)
│
├── conversation/                           # BOUNDED CONTEXT — answer engine (full hexagon)
│   ├── domain/
│   │   ├── model/entity/                   Conversation, Turn
│   │   ├── model/valueobject/              Answer, RetrievedEvidence, GuardrailDecision, Confidence
│   │   ├── service/                        AnswerConversationService, InputGuardrail, OutputGuardrail
│   │   ├── port/in/                        AnswerConversationUseCase (sync + streaming)
│   │   ├── port/out/                       ChatModelPort, KnowledgeRetrievalPort, ConversationMemoryPort
│   │   └── exception/
│   ├── application/service/                ConversationAppService
│   └── infrastructure/
│       ├── adapter/in/rest/                ConversationController (+ SSE, dto/)
│       ├── adapter/out/knowledge/          InProcKnowledgeRetrievalAdapter   ← THE seam + ACL
│       ├── adapter/out/chat/               MistralChatAdapter, OpenAiChatAdapter, OllamaChatAdapter
│       ├── adapter/out/memory/             InMemoryConversationMemoryAdapter
│       └── config/                         ConversationConfig (@Bean wiring)
│
└── shared/                                 # technical cross-cutting ONLY (no shared domain)
    ├── telemetry/                          OTel setup, correlation id
    └── config/                             common bootstrap (profiles, base error handling)
```

**The extraction seam (heart of the Hive-light split):**

```text
conversation.domain.port.out.KnowledgeRetrievalPort
        ▲ implemented by
conversation.infrastructure.adapter.out.knowledge.InProcKnowledgeRetrievalAdapter   (ACL: Chunk → RetrievedEvidence)
        │ calls only
knowledge.domain.port.in.KnowledgeRetrievalUseCase  →  RetrievalService (EmbeddingPort + VectorStorePort)
```

Later extraction = swap `InProcKnowledgeRetrievalAdapter` for a
`RestKnowledgeRetrievalAdapter`; nothing else moves.

**The four internal-design decisions (were parked; now fixed in ADR-0027):**

| Point | Decision | Rationale / ADR |
|---|---|---|
| RAG orchestration | Domain service `AnswerConversationService` sequences **input guardrail → retrieval (seam) → LLM wording → output guardrail** explicitly. Spring AI `QuestionAnswerAdvisor` is **not** the orchestrator (Spring AI = discrete `ChatModelPort` + `EmbeddingPort` only). | Keeps guardrail hooks + seam explicit, testable, per-slice observable — ADR-0014, ADR-0018 |
| Streaming-ready ports | `ChatModelPort` = sync **+** `TokenStream`; `AnswerConversationUseCase` = sync **+** streaming, from day one. Retrieval stays sync. | Deferring SSE (BE-007, Medium) must not force a later domain change — ADR-0013 |
| Conversation memory | Behind `ConversationMemoryPort`; V1 `InMemoryConversationMemoryAdapter` keyed by `conversation_id`, last-N turns, history in **system message**, **current turn excluded**. Redis later = adapter swap. | Avoids greeting/duplication bugs; ADR-0008 |
| Guardrails | Domain services `InputGuardrail` / `OutputGuardrail` returning `GuardrailDecision`; deterministic in V1, LLM-based later behind the same interface. | ADR-0014 |

**ArchUnit boundary (added in BE-002):** `..knowledge.domain..` and
`..conversation.domain..` never import each other; cross-context access only from
`..conversation.infrastructure.adapter.out.knowledge..` onto `knowledge..port.in`;
`..shared..` depends on no context and holds no domain.

## Included Tickets

| Ticket | Title | Role | Priority | Depends on |
|---|---|---|---|---|
| TASK-BE-001 | Decide the backend answer-engine framework (closes OQ-007) + ADR | Decision / Architecture | High | — |
| TASK-BE-002 | Scaffold the Java backend module (hexagonal skeleton, build + ArchUnit green) | Enabler | High | BE-001 |
| TASK-BE-003 | Knowledge-base ingestion socle (pivot + Markdown connector + idempotent sync + pgvector) | Enabler | High | BE-002 |
| TASK-BE-004 | RAG retrieval + domain guardrails before/after (ADR-0014) | Core | High | BE-003 |
| TASK-BE-005 | LLM wording step, provider-agnostic (Mistral API default, Ollama alt), grounded + no invented amounts (DEC-002) | Core | High | BE-004 |
| TASK-BE-006 | Conversation endpoint implementing the ADR-0021 contract + short conversation memory | Core | High | BE-005 |
| TASK-BE-007 | Streaming-token answer (SSE) per ADR-0013 — `backend.first_token` ≠ `backend.request` (RF-021) | Latency | Medium | BE-006 |
| TASK-BE-008 | Wire `voice-agent --backend http` end to end to the real endpoint (stub → real) | Integration | High | BE-006 |
| TASK-BE-009 | Observability: OTel traces/metrics/logs across guardrails, retrieval, LLM (DEC-010, ADR-0010) | Pilot gate | High | BE-004…BE-006 |
| TASK-BE-010 | QA functional + latency report (RAG + LLM slices; composite with a real backend) + adversarial review | Pilot gate | High | BE-006…BE-009 |

## Ticket Detail

### TASK-BE-001 — Decide the backend answer-engine framework (closes OQ-007)

**Status:** ✅ **Done (2026-07-18).** Confirmed at sprint start. Decision recorded in
[ADR-0026](../../docs/architecture/adrs/ADR-0026-backend-runtime-and-ai-framework.md)
(framework: **Spring Boot + Spring AI**) and [ADR-0027](../../docs/architecture/adrs/ADR-0027-backend-modular-decomposition-knowledge-conversation.md)
(modular decomposition). OQ-007 is Decided in both `open-questions/v1-open-questions.md`
and `backlog-index.md`. **Runtime baseline: OpenJDK 17** (Spring Boot 3.4 minimum;
team standard). No engine code in this ticket — it unblocks TASK-BE-002.

> **Decision pre-recorded (2026-07-17):** the framework choice is already captured
> in [ADR-0026](../../docs/architecture/adrs/ADR-0026-backend-runtime-and-ai-framework.md)
> — **Spring Boot + Spring AI** for V1 (Quarkus + LangChain4j deferred to an
> ops/native-image or complex-agentic trigger). OQ-007 is flipped to Decided. This
> ticket now **confirms** the ADR at sprint start and scaffolds accordingly; no
> re-evaluation from scratch unless a re-decision trigger appears.

**Goal:** Choose the framework the Java backend uses for LLM orchestration + RAG:
**Spring AI** vs **LangChain4J** vs another option, and record it as an ADR.

**Scope:**
- Evaluate against explicit criteria: provider-agnostic ports supporting the
  DEC-011 chat providers (**Mistral API `mistral-small-latest` = dev default,
  OpenAI = POC target, Ollama = local alt**) and embeddings = Ollama
  `nomic-embed-text`, 768 dim (DEC-005), pgvector RAG integration,
  **streaming-token** support for the low-latency loop (ADR-0013), guardrail hooks
  (ADR-0014), OpenTelemetry integration (DEC-010), and team familiarity. The
  chosen framework must support Mistral, OpenAI and Ollama with streaming.
- Produce an ADR under `docs/architecture/adrs/` (context, decision, rationale,
  implications, alternatives) and flip OQ-007 to Decided.

**Acceptance:**
- One framework is chosen with documented rationale and trade-offs.
- The ADR states how the choice preserves the provider-agnostic port/adapter
  boundary and supports streaming tokens.
- OQ-007 status updated in `open-questions/v1-open-questions.md` and
  `backlog-index.md`.

**Deliverable:** decision + ADR only, **no engine code**. Blocks BE-002…BE-010.
**Not runtime-affecting** (documentation/decision).

### TASK-BE-002 — Scaffold the Java backend module

**Goal:** Recreate a runnable Java backend on the restart branch (removed on this
branch; reference implementation lives on `main`).

**Scope:**
- Spring Boot 3.4.x, **OpenJDK 17**, Maven, package `com.voicesupport`, **context-first
  hexagonal layout per ADR-0027** (two bounded contexts `knowledge` /
  `conversation`, each a full hexagon; `shared/` for technical cross-cutting only).
  Pure domain, ports `in`/`out`; **per-context bean wiring** (`KnowledgeConfig`,
  `ConversationConfig`) — no global `DomainServiceConfig`; chat auto-configurations
  excluded per project convention.
- Profiles + `application.yml`; chosen framework dependency (Spring AI, from BE-001
  / ADR-0026) in `pom.xml`.
- ArchUnit layer rules **plus the inter-context boundary rules** (see below);
  JUnit 5 with **manual fakes (no Mockito)**; `mvn test` green without DB/Ollama.
- A minimal health endpoint; no business logic yet.

**Acceptance:**
- `mvn test` green on a clean checkout with no external service.
- ArchUnit enforces (a) domain purity (no Spring annotations in domain) and
  dependency direction, and (b) the ADR-0027 boundary: `..knowledge.domain..` and
  `..conversation.domain..` never import each other; cross-context access only from
  `..conversation.infrastructure.adapter.out.knowledge..` onto `knowledge..port.in`;
  `..shared..` depends on no context and holds no domain.
- Health endpoint returns a stable, secret-free response.

### TASK-BE-003 — Knowledge-base ingestion socle

**Goal:** Ingest `knowledge-base/*.md` into pgvector so RAG can retrieve grounded
chunks.

**Scope:**
- Pivot format `SourceDocument` (sourceType, sourceId, title, url, content,
  domain, language, updatedAt, contentHash).
- `KnowledgeSourceConnector` port + `MarkdownFolderConnector` reading
  `knowledge-base/*.md`, `domain` from YAML front-matter (SnakeYAML transitive).
- Shared `TextChunker`; `KnowledgeSyncService` idempotent (skip on identical
  `content_hash`, upsert otherwise, deletion-diff via a `kb_source_state` ledger).
- Storage: one Postgres (`pgvector/pgvector`, port 5433), `vector_store` (Spring
  AI-style, **JSONB** metadata, **768 dim**) + `kb_source_state` ledger.
- **Embedding behind its own replaceable provider port/adapter** (DEC-011/DEC-005),
  config-selectable, **default Ollama `nomic-embed-text` (768)**. The adapter
  boundary makes the provider swap a code/config change; note that switching to a
  different dimension (e.g. `mistral-embed` = 1024) requires recreating
  `vector_store` + re-syncing (dimension is fixed at creation). Endpoints
  `POST /api/knowledge/sync[/{sourceType}]` and one-shot `POST /api/knowledge/ingest`.
- Always store a `domain` metadata value (default `general`) so no chunk is later
  excluded by domain filtering.

**Acceptance:**
- A sync run ingests the three FAQ files; a second run is a no-op (idempotent).
- Every stored chunk carries `domain` metadata; deleting a source removes its
  chunks via the ledger.
- The embedding provider is selected via config behind a replaceable adapter
  (default Ollama `nomic-embed-text`); a fake embedding adapter is used in tests.
- Vector dimension is 768; changing the embedding model is documented as requiring
  a table recreation + re-sync.

### TASK-BE-004 — RAG retrieval + domain guardrails (ADR-0014)

**Goal:** Retrieve relevant chunks for a query and enforce guardrails before and
after retrieval.

**Scope:**
- Query embedding (Ollama) + vector search top-k with a domain filter
  (`domain == X OR general`).
- **Input guardrail** before retrieval: off-topic / dangerous / out-of-scope
  queries get a safe canned response, no retrieval/LLM call.
- **Output guardrail** after wording (wired in BE-005): block answers that leak
  disallowed content; never fabricate billing amounts (DEC-002).
- Keep the domain notion extensible (billing / support / commercial) even though
  V1 focus is billing.

**Acceptance:**
- An in-domain question returns relevant chunks; an off-topic question is refused
  with the canned response and no LLM call.
- Legacy/shared (`general`) chunks are included in results.
- Guardrail decisions are observable (see BE-009).

### TASK-BE-005 — LLM wording step (provider-agnostic, grounded)

**Goal:** Produce the spoken answer text from retrieved chunks, grounded and
safe.

**Scope:**
- Chat model wired via config `voice-support.llm.provider`, built manually in
  `DomainServiceConfig` (chat auto-config excluded); Mistral embedding auto-config
  excluded (embeddings stay Ollama). Providers in scope (DEC-011):
  **`mistral-api` (`mistral-small-latest`) = development default**, **`openai` =
  POC target** (adapter built to the same port; **live validation gated on OpenAI
  credentials, not yet available**), **`ollama` = local/offline alternative**.
  Selectable by config with no domain change.
- System prompt that grounds the answer in retrieved chunks, answers in the
  caller's language, **never states a fabricated amount** (DEC-002), and stays
  concise for voice.
- Emit a `confidence` signal on the contract (provisional; the real proof/answer
  threshold is gated by OQ-002 — reuse the provisional 0.5 policy from ADR-0021).
- Optional: cite the source section(s) used (for the web evidence view later).

**Acceptance:**
- Answers are grounded in KB content and never contain a specific invoice amount.
- Provider is swappable via config without touching the domain.
- A low/absent-evidence case yields a safe, non-committal answer (not an invented
  one).

### TASK-BE-006 — Conversation endpoint (ADR-0021 contract) + memory

**Goal:** Expose the answer engine over the exact HTTP contract the voice runtime
already calls.

**Scope:**
- `POST` endpoint accepting `{transcript, conversation_id, correlation_id,
  channel}` and returning `{text, confidence?}` (see `HttpBackendAdapter` /
  ADR-0021). `x-api-key` accepted if configured.
- Wire input guardrail → retrieval → LLM wording → output guardrail.
- Short conversation memory keyed by `conversation_id`; history placed in the
  **system message** (not the user message) and **excluding the current turn**
  (avoid the greeting/duplication bugs recorded in project history).
- Return safe, contract-shaped responses so the voice runtime never needs raw
  provider text; the runtime maps failures to a spoken degraded turn on its side.

**Acceptance:**
- A request with the four fields returns a grounded `text` (+ `confidence`).
- Multi-turn context is honored (follow-up questions use prior turns), first-turn
  greeting logic behaves (empty history detected correctly).
- No raw transcript/answer or secret appears in responses/logs.

### TASK-BE-007 — Streaming-token answer (SSE, ADR-0013)

**Goal:** Stream the answer tokens so the voice runtime can start TTS on the first
token, reducing perceived latency (RF-021: `backend.first_token` diverges from
`backend.request`).

**Scope:**
- SSE token stream per ADR-0013 alongside the sync endpoint (sync stays available
  for fallback).
- Emit a real `backend.first_token` timing distinct from full-answer completion.

**Acceptance:**
- First token is emitted well before the full answer; the composite
  `time_to_first_audio` uses `backend.first_token`, not full completion.
- Sync path still works for clients that do not stream.

> Priority Medium: if time-constrained, this can slip to the tentative Sprint 8;
> BE-006 (sync) is enough for a functional real answer. Flag at mid-sprint.

### TASK-BE-008 — Wire `voice-agent --backend http` end to end

**Goal:** Replace the stub with the real engine in the running Voice2Voice loop.

**Scope:**
- Point `HttpBackendAdapter` at the running Java backend; document run/compose
  steps (backend + pgvector + Ollama + voice-agent).
- Validate a full spoken turn: question → KB-grounded spoken answer.

**Acceptance:**
- A live web voice turn produces a real, KB-grounded spoken answer (not the stub
  placeholder), under one correlation id end to end.
- The batch/stub paths remain available as fallback.

### TASK-BE-009 — Observability across guardrails, retrieval, LLM

**Goal:** Make the backend's behavior and latency observable per slice (mandatory
for runtime work; DEC-010 / ADR-0010 / ADR-0018).

**Scope:**
- Correlation-id continuity from the voice runtime through the backend.
- Spans for input-guardrail, vector search (retrieval), LLM first token, LLM full
  request, output-guardrail; metrics enabling p50/p95/p99 by channel/provider;
  structured logs with correlation id, outcome, component, sanitized error — never
  raw transcript/answer or secrets.
- Map the new slices onto the ADR-0018 taxonomy (RAG / LLM slices).

**Acceptance:**
- A turn produces a continuous trace across runtime → backend with the RAG and LLM
  slices timed.
- p50/p95/p99 are reportable for retrieval and LLM from collected samples.
- No sensitive data in any log/metric/span attribute.

### TASK-BE-010 — QA functional + latency report + adversarial review

**Goal:** Validate the real answer engine functionally and measure its latency
contribution.

**Scope (use `qa-functional-latency`):**
- Functional scenarios (Gherkin/Behave or Java Cucumber): KB-grounded answer,
  off-topic refusal, degraded on LLM failure, no invented amount, multi-turn
  context, confidence handling.
- Latency report per new slice (retrieval, LLM first token) and an updated
  composite `time_to_first_audio` measured with the **real** backend (vs the stub
  baseline), warm, web channel, with sample size and p50/p95/p99.
- Adversarial code review ≥ 90% before QA acceptance (`adversarial-code-review`).

**Acceptance:**
- All functional scenarios pass; latency reported honestly per slice with the real
  backend cost isolated.
- Adversarial review ≥ 90% (or residual risk explicitly accepted).

## Out Of Scope (gated — stays for later sprints)

| Item | Reason / Gate |
|---|---|
| Customer identity on any channel | OQ-001 (identity source + confidence) — no customer-specific data without it |
| BSS read access to invoices/usage | OQ-003 (BSS availability/granularity) |
| Invoice PDF extraction to structured JSON | OQ-004 + ADR-0005 (deterministic extraction before any amount) |
| Deterministic invoice comparison (EPIC-004) | Depends on BSS + PDF; produces the actual delta |
| Customer-specific amounts in answers | DEC-002 — the LLM never computes amounts; needs extraction + comparison first |
| Real proof/confidence threshold rule | OQ-002 — provisional 0.5 policy reused meanwhile |
| Genesys handoff / telephony | OQ-006 / EPIC-007 (later sprint) |
| Web evidence view (EPIC-008) | Depends on a real comparison to display |

## Sprint Acceptance Criteria

```gherkin
Scenario: The bot answers a generic billing question grounded in the knowledge base
  Given the real conversation backend is running with the knowledge base ingested
  When the customer asks by voice how prorations appear on an invoice
  Then the bot speaks an answer grounded in the knowledge-base content
  And the answer contains no fabricated customer-specific amount
```

```gherkin
Scenario: An off-topic question is safely refused
  Given the real conversation backend
  When the customer asks something outside the supported domains
  Then the bot returns the safe canned response
  And no LLM generation is performed for that turn
```

```gherkin
Scenario: A backend failure still yields a safe spoken turn
  Given the LLM provider is unavailable
  When the customer asks a question
  Then the voice runtime speaks the safe degraded fallback
  And the failure is observable with a correlation id and sanitized error
```

## Definition Of Done (sprint)

- OQ-007 decided with an ADR (TASK-BE-001). ✅ Done (ADR-0026 + ADR-0027).
- Java backend scaffolded; `mvn test` + ArchUnit green (TASK-BE-002).
- Knowledge base ingested idempotently into pgvector (TASK-BE-003).
- RAG retrieval + pre/post guardrails working (TASK-BE-004).
- Grounded, provider-agnostic LLM wording with no invented amounts (TASK-BE-005).
- Conversation endpoint implements the ADR-0021 contract with short memory
  (TASK-BE-006).
- `voice-agent --backend http` produces a real KB-grounded spoken answer end to
  end (TASK-BE-008).
- OpenTelemetry traces/metrics/logs across guardrails/retrieval/LLM, correlation
  id continuity, no sensitive data (TASK-BE-009).
- QA functional + per-slice latency report with the real backend; adversarial
  review ≥ 90% (TASK-BE-010).
- Streaming tokens (TASK-BE-007) done, or explicitly deferred with a recorded
  reason.
- Merge only when the user explicitly asks.

## Open Questions / Dependencies

- **OQ-007** (framework) — lifted by TASK-BE-001 (in-sprint, first ticket).
- **OQ-002** (proof threshold) — provisional 0.5 reused; real rule deferred.
- **OQ-005** (latency acceptance) — relevant to the Entry Condition (Sprint 6).
- **LLM provider (DEC-011):** Mistral API is the dev default; **OpenAI is the POC
  target but its live validation is blocked until OpenAI credentials are
  provided** — the OpenAI adapter is built in-sprint, its live/POC run is deferred.
- Infra: Postgres (`pgvector`, 5433) and Ollama (`nomic-embed-text`) must be
  available for ingestion/retrieval; document local run. Mistral API key for the
  dev default; OpenAI API key pending for the POC.

## Branch Plan

The sprint branch `feat/sprint-7-answer-engine` is cut from
`feat/restart-from-scratch` **after Sprint 6 is validated/merged**. Each ticket is
developed on its own branch (`task/TASK-BE-00X-...`) cut from the sprint branch and
merged back once validated (adversarial review ≥ 90% + QA), following
`docs/operations/development-workflow.md`.

| Ticket | Branch | Status |
|---|---|---|
| TASK-BE-001 | `task/TASK-BE-001-framework-decision` | ✅ Done (2026-07-18) — ADR-0026 + ADR-0027 |
| TASK-BE-002 | `task/TASK-BE-002-backend-scaffold` | 🚧 In progress |
| TASK-BE-003 | `task/TASK-BE-003-kb-ingestion` | Planned |
| TASK-BE-004 | `task/TASK-BE-004-rag-guardrails` | Planned |
| TASK-BE-005 | `task/TASK-BE-005-llm-wording` | Planned |
| TASK-BE-006 | `task/TASK-BE-006-conversation-endpoint` | Planned |
| TASK-BE-007 | `task/TASK-BE-007-streaming-tokens` | Planned (Medium; may defer) |
| TASK-BE-008 | `task/TASK-BE-008-wire-http-backend` | Planned |
| TASK-BE-009 | `task/TASK-BE-009-observability` | Planned |
| TASK-BE-010 | `task/TASK-BE-010-qa-latency` | Planned |
