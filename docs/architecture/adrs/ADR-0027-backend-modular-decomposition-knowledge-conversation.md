# ADR-0027: Backend Modular Decomposition — Knowledge And Conversation Bounded Contexts (Hive-light)

## Status

Accepted (user decision, 2026-07-18). Records the internal decomposition that
TASK-BE-002 (Sprint 7) scaffolds, on top of the framework decision in ADR-0026.

## Context

ADR-0026 chose **Spring Boot + Spring AI** for the V1 answer engine. The remaining
question is **how the backend is structured internally** so it stays maintainable
and microservices-ready without a rewrite (the Hive pattern, see the
`software-architect` skill).

The answer engine spans two responsibilities with **different lifecycles**:

- **Knowledge** — ingest `knowledge-base/*.md` into pgvector and retrieve grounded
  chunks (batch/sync-driven; embeddings and larger corpora can make it CPU/IO
  heavy; ADR-0007, ADR-0006).
- **Conversation** — answer a turn behind the ADR-0021 contract: guardrails
  (ADR-0014), short memory, and a provider-agnostic LLM wording step (DEC-011),
  with streaming tokens for latency (ADR-0013, ADR-0018). This path is
  request/latency-driven.

These are two **bounded contexts**. They may need independent scaling or extraction
later (a heavier retrieval corpus should not force the latency-sensitive answer
path to scale with it). A flat, single-context layout would merge the two
lifecycles and leave no clean extraction seam.

Four internal design points were parked during the architecture discussion and are
decided here: **RAG orchestration, streaming-ready ports, conversation memory,
guardrails.**

## Decision

**Adopt a Hive-light modular monolith with two bounded contexts as top-level
packages, each a full hexagon (context-first layout, per the `software-architect`
skill's Layout B):**

```text
com.voicesupport
├── VoiceSupportApplication            # Spring Boot bootstrap (root)
├── knowledge/                         # bounded context — full hexagon
│   ├── domain/ (model, service, port/in, port/out, exception)
│   ├── application/service
│   └── infrastructure/ (adapter/in/rest, adapter/out/{pgvector,embedding,markdown,persistence}, config)
├── conversation/                      # bounded context — full hexagon
│   ├── domain/ (model, service, port/in, port/out, exception)
│   ├── application/service
│   └── infrastructure/ (adapter/in/rest[+SSE], adapter/out/{knowledge,chat,memory}, config)
└── shared/                            # technical cross-cutting only (telemetry, correlation id)
```

**1 — Single cross-context seam.** The only bridge between the contexts is
`conversation.domain.port.out.KnowledgeRetrievalPort`, implemented by an **INPROC
adapter** in `conversation.infrastructure.adapter.out.knowledge` that calls **only**
`knowledge.domain.port.in.KnowledgeRetrievalUseCase` and carries an
**Anticorruption Layer** (`knowledge` `Chunk` → `conversation` `RetrievedEvidence`).
Vector store, embeddings, chunking and the sync ledger stay **internal to
Knowledge** and are never referenced from Conversation.

**2 — Extraction is an adapter swap.** Extracting Knowledge to its own service means
replacing `InProcKnowledgeRetrievalAdapter` with a `RestKnowledgeRetrievalAdapter`;
the domain, ports, guardrails and orchestration do not change.

**3 — Per-context wiring.** Each context owns its bean-wiring config
(`KnowledgeConfig`, `ConversationConfig`); there is no global `DomainServiceConfig`.
`shared/` holds only technical cross-cutting code — **no shared domain**.

The four parked internal-design points are decided as follows (all consistent with
existing ADRs):

- **RAG orchestration is domain logic, not a framework call.** A domain service
  `AnswerConversationService` (behind `AnswerConversationUseCase`) sequences the
  pipeline explicitly: **input guardrail → `KnowledgeRetrievalPort` → `ChatModelPort`
  wording → output guardrail**. Spring AI's all-in-one `QuestionAnswerAdvisor` is
  **not** used as the orchestrator, so the guardrail hooks (ADR-0014) and the
  Knowledge seam stay explicit, independently testable, and per-slice observable
  (ADR-0018). Spring AI is used only for the discrete `ChatModelPort` (chat client +
  streaming) and `EmbeddingPort` adapters, inside infrastructure.
- **Ports are streaming-ready from day one.** `ChatModelPort` exposes both a sync
  completion and a `TokenStream` streaming method (ADR-0013); `AnswerConversationUseCase`
  exposes both a sync and a streaming answer. This holds even though the SSE endpoint
  (TASK-BE-007) is Medium priority and may defer — deferring SSE must not force a
  later domain change. `KnowledgeRetrievalPort` stays synchronous (retrieval is not
  streamed).
- **Conversation memory lives behind a port.** `ConversationMemoryPort` (out) with a
  V1 `InMemoryConversationMemoryAdapter`, keyed by `conversation_id`, bounded to the
  last N turns. History is injected into the **system message** and **excludes the
  current turn** (avoids the greeting/duplication bugs recorded in project history).
  A Redis adapter (ADR-0008) is a later adapter swap with no domain change.
- **Guardrails are domain services.** `InputGuardrail` (before retrieval) and
  `OutputGuardrail` (after wording) return a `GuardrailDecision` value object, per
  ADR-0014. V1 is deterministic (keyword/policy, no LLM call); an LLM-based guardrail
  can replace the implementation behind the same interface later.

**ArchUnit enforces the boundary:** `..knowledge.domain..` and
`..conversation.domain..` never import each other; cross-context access is allowed
only from `..conversation.infrastructure.adapter.out.knowledge..` onto
`knowledge..port.in`; `..shared..` depends on no context and holds no domain.

## Consequences

**Positive**

- **Independent extractability:** Knowledge can become its own service by swapping
  one adapter (INPROC → REST); nothing else moves. Matches the two contexts'
  divergent scaling profiles.
- **Clean latency attribution:** guardrail, retrieval, LLM first token and full
  wording are distinct, individually instrumented steps (ADR-0018, TASK-BE-009).
- **Testability:** each context and each guardrail/retrieval/wording step is unit-
  testable with manual fakes; the INPROC seam is stubbed exactly like a future REST
  client, so tests move with the extracted module.
- **Provider isolation:** chat/embedding providers (DEC-011) stay in infra adapters
  behind ports; the framework and providers remain swappable.

**Negative / risks**

- **More packages and ports up front** than a flat layout, and the ACL mapping
  (`Chunk` → `RetrievedEvidence`) is boilerplate that only pays off at extraction —
  accepted as the Hive's explicit, deliberate cost.
- **Two-context ArchUnit rules must be maintained** as the code grows (and updated
  if a third context appears).

**Re-decision triggers**

- A third bounded context emerges (e.g., billing/BSS/comparison for customer-specific
  invoice explanation) — apply the same pattern, add a context package and its seam.
- If, contrary to expectation, the contexts never diverge in scaling and the ACL
  proves pure overhead, collapse to a single context via a new ADR.

## Alternatives Considered

- **Single flat context (layer-first, Layout A):** rejected. Merges two lifecycles,
  leaks retrieval internals (vector store, embeddings) into the conversation path,
  offers no clean extraction seam, and makes latency attribution harder.
- **Direct service call between contexts (no port + ACL):** rejected. Couples the two
  domains, breaks independent extractability, and violates the Hive's INPROC boundary.
- **Spring AI `QuestionAnswerAdvisor` as the orchestrator:** rejected *as the
  orchestrator*. It hides retrieval + generation inside a single framework call,
  bypassing the ADR-0014 guardrail hooks and the Knowledge seam and reducing per-slice
  observability. It may still be used as an implementation detail *inside* the
  `ChatModelPort` adapter if ever beneficial, but never as the cross-context
  orchestration.
- **Layer-first with contexts as sub-packages under a shared `domain/`:** rejected.
  Keeps a shared top-level layer that dilutes ownership and makes the extraction unit
  ambiguous; context-first makes the movable unit obvious (`knowledge/`).

## Related Documents

- `docs/architecture/adrs/ADR-0026-backend-runtime-and-ai-framework.md`
- `docs/architecture/adrs/ADR-0021-conversation-backend-answer-contract.md`
- `docs/architecture/adrs/ADR-0014-domain-guardrails-before-and-after-rag.md`
- `docs/architecture/adrs/ADR-0013-tokenstream-and-backend-sse-streaming-contract.md`
- `docs/architecture/adrs/ADR-0007-source-document-knowledge-sync.md`
- `docs/architecture/adrs/ADR-0008-redis-active-sessions-postgres-durable-events.md`
- `docs/architecture/adrs/ADR-0006-mistral-chat-and-ollama-embeddings.md`
- `docs/architecture/adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md`
- `.cursor/skills/software-architect/SKILL.md` (Layout B, the Hive, enforcement)
- `product-backlog/sprints/sprint-7-answer-engine.md` (TASK-BE-002…BE-006)
- `product-backlog/decisions/v1-decisions.md` (DEC-011, DEC-005)
