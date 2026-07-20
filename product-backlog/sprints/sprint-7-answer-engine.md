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

**Adversarial review (2026-07-18):** ✅ **94/100 — QA gate PASS.** No blocking
findings. Scaffold matches ADR-0027 (context-first, two hexagons + `shared/`), the
INPROC seam + ACL is present, `mvn test` green (19 tests) on OpenJDK 17 with no
DB/Ollama. Non-blocking notes: seam ArchUnit rule allows `knowledge.domain.model`
(the published API's return types) in addition to `port.in`; `archunit.properties`
sets `failOnEmptyShould=false` for still-empty packages (revisit once populated in
BE-003+); empty per-context `@Configuration` classes anchor wiring for later
tickets; the seam is intentionally unwired until BE-006. Not runtime-affecting
(no conversation/voice slice yet) — OTel instrumentation deferred to BE-009.

**QA (2026-07-18):** ✅ **PASS.** (1) `mvn test` → BUILD SUCCESS, 19/19, no external
service. (2) Boundary effectiveness proven by a negative probe: a temporary
`conversation.domain` class importing `knowledge` made `ContextBoundaryTest` fail
(2 rules fired), and removing it restored green — the guardrail is not vacuous.
(3) Health endpoint returns `{"status":"UP","service":"voice-support-backend"}`,
secret-free. No latency slice applies to an enabler scaffold.

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
- **Embedding is provider-replaceable at the Spring AI `EmbeddingModel` bean**
  (DEC-011/DEC-005), config/profile-selectable, **default Ollama `nomic-embed-text`
  (768)**. Decision (validated with the proven `main` design): the Spring AI pgvector
  `VectorStore` performs embedding internally via the configured `EmbeddingModel`, so
  the domain stays embedding-agnostic behind `VectorStorePort` — no separate domain
  `EmbeddingPort`. Swapping providers is an infra bean/config change; the domain is
  untouched. Note that switching to a different dimension (e.g. `mistral-embed` = 1024)
  requires recreating `vector_store` + re-syncing (dimension is fixed at creation).
  Endpoints `POST /api/knowledge/sync[/{sourceType}]` and one-shot
  `POST /api/knowledge/ingest`.
- Always store a `domain` metadata value (default `general`) so no chunk is later
  excluded by domain filtering.

**Acceptance:**
- A sync run ingests the three FAQ files; a second run is a no-op (idempotent).
- Every stored chunk carries `domain` metadata; deleting a source removes its
  chunks via the ledger.
- The embedding provider is config/profile-selectable at the Spring AI
  `EmbeddingModel` bean (default Ollama `nomic-embed-text`); domain unit tests fake
  `VectorStorePort` (no embedding needed offline), so `mvn test` requires no infra.
- Vector dimension is 768; changing the embedding model is documented as requiring
  a table recreation + re-sync.

**Result (2026-07-18) — live-validated on Postgres `pgvector/pgvector:pg16` (5433)
+ native Ollama `nomic-embed-text`:**
- Clean sync #1 → `{"processed":3,"ingested":3,"skipped":0,"deleted":0}`; sync #2 →
  `{...,"ingested":0,"skipped":3}` (idempotent). Chunks: billing 12, commercial 12,
  support 17 — every chunk carries a non-null `domain` (no legacy NULLs).
- Deletion-diff: an injected stale source is removed on the next sync
  (`deleted:1`, purged from both `vector_store` and the `kb_source_state` ledger).
- One-shot `POST /api/knowledge/ingest` (multipart) stores the chunk with its domain.
- `mvn test` green (34 tests) with **no infra** (domain fakes; `@WebMvcTest` health slice).
- Local dev infra added: `docker-compose.yml` (Postgres pgvector + Ollama).
- Delivered in two green increments: (1) pure domain core + Markdown connector;
  (2) Spring AI pgvector + Ollama embedding + JPA ledger + REST + per-context wiring.

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

**Result (2026-07-18) — live-validated on Postgres `pgvector/pgvector:pg16` (5433)
+ native Ollama `nomic-embed-text` (41 KB chunks: support 17 / billing 12 / commercial 12):**
- **Retrieval (knowledge context):** `VectorSearchPort` + `KnowledgeRetrievalService`
  implement the `KnowledgeRetrievalUseCase` seam. `PgVectorStoreAdapter.search` does
  query-embed + pgvector top-k with a domain filter `domain == X OR general`
  (null/blank domain = no restriction). `KnowledgeChunk`/`RetrievedEvidence` now carry
  the similarity `score`.
- **Guardrails (conversation context):** `InputGuardrail` (pre-retrieval, ADR-0014)
  → `GREETING` / `OFF_TOPIC` / `INAPPROPRIATE` / `PASS`; `RetrievalConfidenceGuardrail`
  (post-retrieval) → `LOW_CONFIDENCE` on empty/weak evidence (provisional threshold
  0.5, config `voice-support.conversation.confidence-threshold`, gated by OQ-002).
  `RetrievalGroundingService` (application) composes them: blocked inputs short-circuit
  **before** any embedding/vector call.
- **Surface + observability:** `POST /api/conversation/retrieve` returns the guardrail
  verdict + grounded evidence; structured `[GROUNDING]` logs expose
  `domain / top_k / answerable / verdict / hits / best_score / duration_ms` (full OTel
  traces/metrics = BE-009). The LLM wording + memory + streaming endpoint stays BE-006.
- **Live scenarios:** (1) in-domain billing → 3 chunks, `PASS`, warm ~40–60 ms /
  cold ~685 ms; (2) weather → `OFF_TOPIC`, 0 hits, 1 ms (no retrieval); (3) `Bonjour`
  → `GREETING`, 0 ms; (4) "fabriquer une bombe" → `INAPPROPRIATE`, 0 ms; (5) `general`
  chunk surfaced on a `support` query (OR-filter); (6) billing query returned billing
  chunks only (domain isolation); (7) `LOW_CONFIDENCE` fired end-to-end with threshold
  raised to 0.99. **Finding:** nomic-embed cosine scores cluster ~0.65–0.79, so the
  provisional 0.5 threshold mainly guards near-empty retrieval — the discriminating
  answer threshold is OQ-002.
- `mvn test` green (78 tests) with **no infra** (domain fakes + `@WebMvcTest` slice):
  `InputGuardrailTest` (23), `RetrievalConfidenceGuardrailTest` (4),
  `RetrievalGroundingServiceTest` (5), `KnowledgeRetrievalServiceTest` (4). ArchUnit
  context boundary held (seam wiring moved into the seam package `KnowledgeSeamConfig`).
- **Adversarial review 93/100 (QA gate PASS)** after remediation (commit `4de737f`):
  added `RetrievalControllerTest` (`@WebMvcTest`, imports `JacksonConfig` so the
  snake_case contract is exercised); `domain="general"` now filters to the shared
  domain only (no cross-domain leak); `[GROUNDING]` score formatted with `Locale.ROOT`.
  `mvn test` green (80). Deferred non-blocking findings: correlation id + OTel →
  **TASK-BE-009**; REST error contract / degraded-mode leak → **TASK-BE-012** (created).

**QA — functional + latency (2026-07-19): GO.**
- **Functional (BDD):** `conversation-grounding.feature` — 6 product-observable
  Cucumber scenarios wired to domain services + fakes (no infra), all green in
  `mvn test` (**86 tests**, BDD suite 11 = 5 KB ingestion + 6 grounding): in-domain →
  grounded answer; off-topic → refused, no retrieval; unsafe → refused; greeting →
  handled directly; weak evidence → low-confidence + advisor offer; shared `general`
  chunk grounds a cross-domain answer.

  | Acceptance criterion | Status | Evidence |
  |---|---|---|
  | In-domain question returns relevant chunks | PASS | BDD `in-domain`; live scenario 1 |
  | Off-topic refused, no LLM/retrieval call | PASS | BDD `no retrieval`; live `duration_ms=0` |
  | Shared `general` chunks included | PASS | BDD `shared general`; live scenario 5 |
  | Guardrail decisions observable | PASS (interim) | `[GROUNDING]` logs; full OTel → BE-009 |

- **Latency (live, Postgres pgvector 5433 + native Ollama `nomic-embed-text`, web/local,
  provider=ollama embeddings, warm cache):**

  | Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
  |---|---:|---:|---:|---:|---|---|
  | RAG retrieval (query-embed + pgvector top-k) | 30 ms | 37 ms | 37 ms | 26 | Warm | `verdict=PASS`; tight band |
  | Input-guardrail refusal (no retrieval) | 0 ms | 0 ms | 0 ms | 10 | Warm | `OFF_TOPIC`; proves no embed/search on block |
  | First embed after idle (Ollama load) | — | — | — | 1 | Cold | one-off ~685–791 ms model warm-up, not per-call |

  RAG retrieval slice is well within budget; it is one contributor to the ADR-0018
  voice composite (STT/LLM/TTS measured separately). Cold cost is a one-off Ollama
  warm-up. No sensitive data in logs (question/evidence text not logged).
- **Residual risks:** correlation id + OTel spans/metrics (BE-009); degraded-mode error
  contract if Ollama/pgvector down (BE-012); definitive answer/confidence threshold
  (OQ-002 — provisional 0.5 in effect).

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

**Result (2026-07-19) — implementation + tests + live validation done (branch
`task/TASK-BE-005-llm-wording`); adversarial review + QA gate next.**
- **Wording port + adapters (conversation infra):** `AnswerGeneratorPort` (domain
  out) with `AbstractChatClientAnswerAdapter` (builds the grounded system message from
  `RetrievedEvidence`, history goes in the system message — not the user turn) +
  `MistralAnswerAdapter` / `OllamaAnswerAdapter`. Provider selected by
  `voice-support.llm.provider` in `LlmConfig` (Mistral chat model built manually);
  `VoiceSupportApplication` now excludes the Mistral chat/embedding/moderation
  auto-configs so **embeddings stay Ollama (768d)** and chat is wired by hand. Added the
  `spring-ai-starter-model-mistral-ai` dependency.
- **Output guardrail (DEC-002):** `OutputGuardrail` (domain) blocks any currency amount
  present in the answer but absent from the evidence (`UNGROUNDED` verdict → safe
  fr/en hand-off), so a fabricated figure is never voiced even if the model produces one.
  The provider prompt also forbids stating an unbacked amount — two layers of DEC-002.
- **Application + surface:** `AnswerService` (implements `AnswerQuestionUseCase`) composes
  BE-004 grounding → LLM wording → output guardrail → `GeneratedAnswer(text, confidence,
  grounded)`; confidence = retrieval best score (provisional, ADR-0021 / OQ-002). Blocked
  or ungrounded cases return a safe fallback (`grounded=false`, no confidence), never an
  invented answer. Exposed at `POST /api/conversation/answer` with structured `[ANSWER]`
  logs (`domain / top_k / grounded / confidence / chars / duration_ms`); the full ADR-0021
  contract (exact field names, api-key, memory, streaming) stays **BE-006**.
- **Live validation** (Postgres `pgvector` 5433 + Ollama embeddings, **real Mistral API
  `mistral-small-latest`**, 41 KB chunks): (1) in-domain billing → grounded FR answer,
  `confidence≈0.75`, LLM ~1.7 s; (2) "combien exactement vais-je payer" → model refuses
  and offers a conseiller, **no amount invented** (DEC-002); (3) off-topic → canned
  fallback, `grounded=false`, no LLM (~0–3 ms); (4) English support question → grounded
  **English** answer (`confidence≈0.70`), language follows the caller; (5) obscure
  question → refused. Grounded LLM turns ~0.8–1.7 s (Mistral cloud is the dominant slice);
  blocked inputs short-circuit with no LLM/retrieval.
- `mvn test` green (**102 tests**, no infra): `OutputGuardrailTest` (5), `AnswerServiceTest`
  (4), `AbstractChatClientAnswerAdapterTest` (2), `AnswerControllerTest` (`@WebMvcTest`,
  imports `JacksonConfig`) (2); BDD suite 14 (added `answer-wording.feature`: grounded
  wording / DEC-002 amount block / blocked input never calls the LLM). ArchUnit + context
  boundary held.
- **Provider swap:** `openai` = POC target, adapter to the same port, **live validation
  gated on OpenAI credentials (not yet available)**; `ollama` chat = local alternative
  (selectable, `llama3.1:8b` not pulled on this machine). Swap is config-only, no domain
  change (unit-covered).
- **Adversarial review 93/100 (QA gate PASS).** No blocking finding. Remediated Low
  finding: an empty LLM output or an explicit transfer/refusal answer is now surfaced as a
  safe hand-off (`grounded=false`, no confidence) via `OutputGuardrail.isNonAnswer` instead
  of being voiced as a grounded answer with a confidence signal (the adapter no longer
  substitutes a canned sentence). `mvn test` green (**105**, OutputGuardrail 6 / AnswerService
  6). Non-blocking findings deferred: LLM call timeout + degraded-mode contract → **BE-012**;
  correlation id + OTel → **BE-009**; provider-swap not automated-tested (covered by design).
- **Residual risks:** correlation id + OTel spans/metrics (BE-009); degraded-mode error
  contract + LLM timeout if Mistral/Ollama/pgvector down or slow (BE-012); definitive
  answer/confidence threshold (OQ-002 — provisional 0.5 in effect); conversation memory (BE-006).

**QA — functional + latency (2026-07-19): GO.**
- **Functional (BDD):** `answer-wording.feature` — 3 product-observable Cucumber scenarios
  wired to domain fakes (no infra), green in `mvn test` (**105 tests**, BDD suite 14):
  grounded wording from strong evidence; DEC-002 amount block → safe hand-off; blocked
  input never calls the LLM.

  | Acceptance criterion | Status | Evidence |
  |---|---|---|
  | Answers grounded in KB, never a specific invoice amount | PASS | BDD amount-block; live: "combien exactement" → hand-off, **no figure** |
  | Provider swappable via config, no domain change | PASS (design) | `voice-support.llm.provider` → `LlmConfig`; embeddings stay Ollama. OpenAI **gated creds**; Ollama chat not pulled |
  | Low/absent-evidence → safe non-committal answer | PASS | live: off-topic + obscure → hand-off (`grounded=false`), never invented |
  | Answer in caller's language, concise for voice | PASS | live: EN question → grounded EN answer |

- **Latency (live, Postgres pgvector 5433 + Ollama embeddings, **real Mistral API
  `mistral-small-latest`**, web/local, warm cache; server-side `[ANSWER] duration_ms`):**

  | Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
  |---|---:|---:|---:|---:|---|---|
  | Grounded answer (retrieval + LLM wording + guardrails) | 1088 ms | 1592 ms | 1865 ms | 17 | Warm | Mistral cloud is the dominant contributor (retrieval ~40 ms) |
  | Input-guardrail short-circuit (no LLM/retrieval) | 0 ms | 0 ms | 0 ms | 6 | Warm | off-topic caught by keywords → 0 ms, proves no embed/LLM on block |
  | Post-LLM safe hand-off (off-topic passthrough) | 649 ms | 1515 ms | — | 5 | Warm | novel off-topic not caught by keywords → retrieval+LLM → refusal → `grounded=false` |

  LLM wording (~1.1 s p50 / ~1.6 s p95) is the dominant slice of the ADR-0018 voice
  composite; model/provider choice is the latency lever (STT/TTS measured separately).
  No sensitive data in logs (question/answer/evidence text not logged).
- **QA finding (Low, non-blocking):** the input guardrail is keyword-based, so a novel
  off-topic question (recipe, sports) it does not recognize still reaches retrieval + LLM
  and is handled as a **safe non-grounded hand-off** (never a wrong grounded answer), but at
  LLM latency + token cost. Product-safe; flag for guardrail-coverage / semantic-gate tuning
  (OQ-002 / a future guardrail follow-up), not a BE-005 blocker.
- **Recommendation:** GO for BE-005. Merge-ready on the user's explicit request.

**User validation (2026-07-19): validated.** All gates passed (implementation → 105
tests → adversarial review 93/100 → QA GO). Merged into `feat/sprint-7-answer-engine`.

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

**Implementation (2026-07-19) — branch `task/TASK-BE-006-conversation-endpoint`:**
- **Endpoint:** `POST /api/conversation/converse` (`ConverseController`) binds the
  ADR-0021 snake_case contract (`transcript`, `conversation_id`, `correlation_id`,
  `channel`) via the shared `JacksonConfig` and returns `{text, confidence?}`
  (`confidence` omitted when the answer is a guardrail fallback, `NON_NULL`). A
  blank transcript short-circuits to a safe, digit-free listen prompt (no
  embedding/LLM). `x-api-key` is enforced only when
  `voice-support.conversation.api-key` is set (open on the pilot host otherwise).
- **Memory:** `ConversationTurn` VO + `ConversationMemoryPort` (out) +
  `InMemoryConversationMemoryAdapter` (process-local, bounded: `max-turns`
  exchanges/conversation, LRU cap `max-conversations`, thread-safe). Prior turns
  are read **before** the current turn is appended, so the history passed to the
  LLM **excludes the current turn** and `already_greeted` is derived from
  non-empty history — closing the greeting/duplication bugs in project history.
- **Orchestration:** `ConverseUseCase` / `ConversationService` reuses the BE-005
  pipeline. `AnswerQuestionUseCase.answer(...)` gained a `history` parameter
  (placed in the system message by the wording adapter); retrieval spans all
  domains (`domain=null`, `topK=4`, no classifier in V1 here). Grounding, DEC-002
  output guardrail and safe fallbacks are inherited unchanged.
- **Observability:** privacy-safe `[CONVERSE]` structured log per turn
  (`channel`, `conversation_id`, `correlation_id`, `grounded`, `confidence`,
  `chars`, `duration_ms`) — never the raw transcript/answer or a secret.
- **Tests:** +16 (total **121**, `mvn test` green, no DB/Ollama needed):
  `ConversationServiceTest` (history/greeting/isolation/record),
  `InMemoryConversationMemoryAdapterTest` (bounded, LRU, blank-id safe, ordering),
  `ConverseControllerTest` (contract + blank prompt), `ConverseControllerApiKeyTest`
  (401 missing/wrong, 200 matching), BDD `conversation-memory.feature` (3 scenarios).
- **Live validation (Postgres pgvector 5433 + Ollama embeddings + real Mistral
  `mistral-small-latest`, warm; server-side `[CONVERSE] duration_ms`):**
  - T1 `Bonjour` → greeting, `grounded=false`, no LLM (guardrail short-circuit, ~1 ms).
  - T2 `Pourquoi ma facture a augmenté ce mois-ci ?` → grounded answer
    (`confidence≈0.74`, 2.14 s), **no invented amount** (points to the customer area / 3900).
  - T3 `Et comment puis-je éviter cela le mois prochain ?` → the follow-up correctly
    resolves `cela` to T2's bill increase (**multi-turn context honored**),
    `grounded=true` (`confidence≈0.68`, 1.21 s).
  - DEC-002 spot-check `Combien exactement vais-je payer ?` → safe hand-off, **no figure**.
  - Blank transcript → safe listen prompt (200). `[CONVERSE]` logs carry lengths
    + correlation id only (no transcript/answer text).
- **Adversarial review (2026-07-19): 92/100, QA gate Pass.** No blocking finding, no
  functional bug, no boundary violation; tests at every level; behavior observable via
  privacy-safe `[CONVERSE]` logs. Residuals (all ticketed/accepted): OTel spans+metrics
  deferred to BE-009 (latency still derivable from `duration_ms`), Java-side LLM
  timeout + global degraded contract deferred to BE-012 (a hard failure returns 500 and
  the voice runtime degrades it to a safe spoken turn), non-constant-time api-key compare.
- **Review remediation (Medium finding fixed):** a missing/blank `conversation_id` is now
  **stateless** (empty history, no persistence) instead of a shared `"default"` memory
  bucket — removes the cross-caller context-bleed privacy risk. Added
  `ConversationServiceTest.blankConversationIdIsStateless` +
  `ConverseControllerTest.missingConversationIdIsAccepted`. Tests now **123** green.
- **QA functional + latency (2026-07-19): GO.** Regression: 123 automated tests green
  (unit + `@WebMvcTest` contract + BDD). Live acceptance (Postgres pgvector 5433 + Ollama
  embeddings + real Mistral `mistral-small-latest`, web/local, warm):

  | # | Scenario | Result |
  |---|---|---|
  | F1 | First-turn `Bonjour` | Greeting, `grounded=false`, guardrail short-circuit (no LLM) |
  | F2 | `Pourquoi ma facture a augmenté ?` | Grounded (`conf≈0.74`), **no invented amount** |
  | F3 | Follow-up `Comment éviter cela ?` | Resolves `cela` → F2 (**context honored**); grounded |
  | F4 | `Combien exactement vais-je payer ?` | Safe hand-off, **no figure** (DEC-002) |
  | F5 | Off-topic (capitale de l'Australie) | Safe non-grounded domain refusal |
  | F6 | Blank transcript | Safe listen prompt (200) |
  | F7 | Missing `conversation_id` | Stateless, grounded answer (200) — no shared bucket |
  | K1/K2/K3 | `x-api-key` absent / wrong / correct | 401 / 401 / 200 (secret never logged) |

  - **DEC-002 nuance validated:** F3 voiced "pack international (5€/mois)" — this figure is
    **grounded** in `commercial-faq.md` (KB catalog tariff), so the output guardrail
    correctly allowed it, while F4 (customer-specific invoice amount) is still refused.
    Behavior is correct: KB-backed tariffs pass, fabricated invoice figures never do.

- **Latency (live, warm; server-side `[CONVERSE] duration_ms`):**

  | Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
  |---|---:|---:|---:|---:|---|---|
  | Grounded converse turn (retrieval + LLM wording + guardrails) | 570 ms | 1338 ms | 1460 ms | 15 | Warm | Mistral cloud dominates; retrieval ~tens of ms |
  | Guardrail short-circuit (greeting/off-topic/blank) | 0 ms | 0 ms | 0 ms | 6 | Warm | No embed/retrieval/LLM — deterministic keyword path |

  Correlation-id continuity verified (all `[CONVERSE]` lines carried the id, none `n/a` for
  identified turns). No sensitive data in logs (transcript/answer text and api-key absent).
- **QA recommendation: GO for BE-006.** Residuals unchanged and ticketed: OTel spans+metrics
  (BE-009), Java-side LLM timeout + global degraded contract (BE-012). Not pilot blockers.
- **Status:** implementation + 123 tests + adversarial review (92/100, remediated) + QA
  functional & latency (GO) done. **Merge-ready** — awaiting the user's explicit merge request.

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

**Implementation (2026-07-19, `task/TASK-BE-009-observability`, ADR-0028):**
- `shared/observability`: `CorrelationIdFilter` (reuse `X-Correlation-Id` header or
  generate a UUID; MDC + response echo; always cleared) + `CorrelationId` helper.
  `/converse` uses the runtime's **body** `correlation_id` as authoritative (overwrites
  the response header) and propagates the `channel`, so a turn shares one id end to end.
- `BackendTelemetry`: records the `voice_support.slice` Micrometer timer tagged
  `slice`/`channel`/`provider`/`outcome` with client-side p50/p95/p99, plus a privacy-safe
  `[TELEMETRY]` structured log (durations only — no transcript/answer/secret). Slices:
  `retrieval` (seam adapter), `llm_wording` (provider adapter, provider tag),
  `backend_request` (composite, `ConverseController`). The deterministic input/output
  guardrail decision stays captured as the request `grounded` outcome + `[GROUNDING]`
  log (no separate timer until it carries real latency).
- Exposed via `spring-boot-starter-actuator` (`health,info,metrics`); no exporter for
  the pilot — a Micrometer Tracing→OTel bridge is the documented upgrade path to spans.
- `ContextBoundaryTest` extended so the knowledge seam may depend on context-agnostic
  `com.voicesupport.shared..` (`sharedMustNotDependOnAnyContext` still forbids the reverse).
- Tests: `CorrelationIdFilterTest`, `BackendTelemetryTest`, `ConverseController` header
  echo; adapter/config wiring updated. **`mvn test` 130 green.**
- **Live-verified** (pgvector 5433 + Ollama + Mistral, warm): one correlation id
  (`cid-be009-live`) across `retrieval`/`llm_wording`/`backend_request` slice logs;
  header echo confirmed; `/actuator/metrics/voice_support.slice.percentile` reported
  retrieval p50 63 ms / p95 703 ms and LLM p50 906 ms / p95 1040 ms by `phi` tag.
- **Adversarial review (2026-07-20): 93/100 — QA gate Pass.** No blocking findings.
  Non-blocking (all ticketed/accepted): client-controlled `channel` used as a metric
  tag (cardinality risk — bounded today, our own runtime; recommend allow-listing),
  unauthenticated `/actuator/metrics` (fine local pilot), `retrieval` provider tag
  `pgvector` folds the embedding sub-step (documented in ADR-0028).
- **QA functional + latency (2026-07-20): GO.** Regression 135 tests green. Live
  (pgvector 5433 + Ollama + real Mistral, web, warm): one correlation id across
  `retrieval`/`llm_wording`/`backend_request` slices + `[CONVERSE]` per turn, header
  echoed; no transcript/answer/secret in logs (only `provider=mistral-api` tag). Live
  per-slice latency (warm, 16 samples, client-side percentile buckets are coarse):

  | Slice | p50 | p95 | Sample | Notes |
  |---|---:|---:|---:|---|
  | retrieval | 63 ms | 703 ms | 16 | pgvector + Ollama embed; p95 skewed by first cold call |
  | llm_wording | 1107 ms | 2919 ms | 16 | Mistral cloud dominates |
  | backend_request | 1107 ms | 2919 ms | 16 | LLM-bound; retrieval ~tens of ms |
- **Status:** implementation + 135 tests + adversarial review (93/100) + QA (GO) done.
  **Merge-ready** — awaiting the user's explicit merge request.

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
| TASK-BE-002 | `task/TASK-BE-002-backend-scaffold` | ✅ Validated by user (2026-07-18) — review 94/100 + QA PASS; merge-ready (awaiting explicit merge) |
| TASK-BE-003 | `task/TASK-BE-003-kb-ingestion` | ✅ Validated by user (2026-07-18) — adversarial review 94/100 + QA PASS; `mvn test` 42 green (5 Cucumber BDD scenarios); live latency cold sync p50 1422 ms / warm 5 ms / one-shot ingest 27 ms; merge-ready (awaiting explicit merge) |
| TASK-BE-004 | `task/TASK-BE-004-rag-retrieval-guardrails` | ✅ Validated + merged into `feat/sprint-7-answer-engine` (2026-07-19, ff; branch deleted) — adversarial review 93/100 + QA GO; `mvn test` 86 green (6 grounding Cucumber scenarios); live RAG retrieval p50 30 ms / p95 37 ms (warm), guardrail refusal 0 ms |
| TASK-BE-005 | `task/TASK-BE-005-llm-wording` | ✅ Validated by user + merged into `feat/sprint-7-answer-engine` (2026-07-19) — provider-agnostic grounded LLM wording (DEC-002); adversarial review + QA GO |
| TASK-BE-006 | `task/TASK-BE-006-conversation-endpoint` | ✅ Validated by user + merged into `feat/sprint-7-answer-engine` (2026-07-19, merge commit) — ADR-0021 endpoint + short memory; review 92/100 (remediated) + QA GO; 123 tests green |
| TASK-BE-007 | `task/TASK-BE-007-streaming-tokens` | Planned (Medium; may defer) |
| TASK-BE-008 | `task/TASK-BE-008-wire-http-backend` | Planned |
| TASK-BE-009 | `task/TASK-BE-009-observability` | ✅ Adversarial review 93/100 + QA GO (2026-07-20), ADR-0028 — correlation-id continuity + `voice_support.slice` metrics (retrieval/LLM/request, p50/p95/p99); 135 tests green; merge-ready (awaiting explicit merge) |
| TASK-BE-010 | `task/TASK-BE-010-qa-latency` | Planned |
| TASK-BE-012 | `task/TASK-BE-012-backend-error-contract` | ✅ Adversarial review 92/100 + QA GO (2026-07-20), branched from BE-009 — sanitized `GlobalExceptionHandler`/`ErrorResponse` (400/503, no leak) + `@NotBlank` + hard LLM timeout; RestClient→503 gap fixed in review; 135 tests green; merge-ready (awaiting explicit merge) |
