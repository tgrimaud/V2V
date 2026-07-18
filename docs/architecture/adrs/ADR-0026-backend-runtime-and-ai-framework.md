# ADR-0026: Backend Runtime And AI Orchestration Framework (Spring Boot + Spring AI For V1)

## Status

Accepted (user decision, 2026-07-17). Resolves OQ-007. Records the decision that
TASK-BE-001 (Sprint 7) implements.

## Context

The Sprint 7 answer engine (EPIC-005) needs the Java backend to orchestrate an
LLM + RAG pipeline behind the existing conversation contract (ADR-0021). Choosing
how to build it raised two **distinct but linked** questions that were initially
conflated:

- **Axis 1 — backend runtime:** Spring Boot vs Quarkus vs Micronaut.
- **Axis 2 — AI orchestration library:** Spring AI vs LangChain4j.

The coupling constraint:

- **Spring AI requires Spring Boot.**
- **LangChain4j is runtime-agnostic** (Spring Boot, Quarkus, Micronaut, plain
  Java) and has a first-class Quarkus extension.

So "switch to Quarkus" only delivers value if it is paired with LangChain4j; it is
effectively **two pivots at once**, away from the team's current stack.

Decision criteria for this project:

- provider-agnostic ports for chat (Mistral default, OpenAI POC target, Ollama
  alternative — DEC-011) and a replaceable embedding provider (Ollama
  `nomic-embed-text`, 768 — ADR-0006);
- RAG over pgvector (ADR-0007) with domain guardrails before/after retrieval
  (ADR-0014);
- streaming tokens for the low-latency voice loop (ADR-0013 / ADR-0018);
- **mandatory** OpenTelemetry traces, metrics and structured logs (DEC-010 /
  ADR-0010);
- hexagonal architecture with a pure, framework-free domain;
- team familiarity and workspace consistency.

Both frameworks are production-ready (2026) and cover the full functional need
(Mistral, OpenAI, Ollama, RAG, pgvector, streaming, memory, tool calling, MCP).
The differentiators for V1 are integration, observability, and team fit — not raw
capability.

## Decision

**V1 uses Spring Boot as the backend runtime and Spring AI as the AI orchestration
library.**

- The answer engine is built on Spring Boot 3.4.x (OpenJDK 17), hexagonal, with domain
  services wired as `@Bean`s in `DomainServiceConfig` (chat auto-configurations
  excluded; Mistral embedding auto-config excluded so embeddings stay Ollama).
- Spring AI provides the chat client, the RAG advisor over pgvector, streaming
  (Reactor `Flux`), and native Micrometer/OpenTelemetry instrumentation.
- All providers stay behind the project's **replaceable ports** (DEC-005,
  ADR-0021, ADR-0006): the Spring AI dependency lives only in the infrastructure
  layer, never in the domain, so the framework itself remains swappable.

**Quarkus + LangChain4j is deliberately not adopted for V1** and is reconsidered
only if a concrete trigger appears (see Consequences / Alternatives).

## Consequences

**Positive**

- **Native fit with the existing stack:** Spring Boot conventions, the
  `java-backend-developer` skill, ArchUnit rules, profiles and manual bean wiring
  all apply unchanged; the sibling `cursor-usage-dashboard` already runs Spring AI,
  so ramp-up is minimal.
- **Observability by default (DEC-010):** Spring AI exposes Micrometer + OTel
  natively (including vector-store instrumentation) and **does not log prompt or
  completion content by default**, aligning with the project's no-PII /
  sanitization rules.
- **Fast RAG for V1:** the `QuestionAnswerAdvisor` over pgvector is sufficient for
  the FAQ-grade knowledge base; low setup cost.
- **Streaming ready:** reactive `Flux` supports the token streaming needed for
  `backend.first_token` (ADR-0013, TASK-BE-007).
- **Reversible by design:** the domain is framework-free; the runtime lives only in
  infra/adapter, so a future runtime change touches the infrastructure layer, not
  the business core.

**Negative / risks**

- **Spring AI API churn** across milestones is a known irritant (previously hit:
  `TokenTextSplitter.Builder`, `AssistantMessage` package move, `ChatClient`
  interface changes). Mitigation: pin the version and verify the real API
  (`javap`/IDE) before using a builder or import.
- **Narrower provider/vector-store catalog** than LangChain4j and **less granular
  RAG/agentic control**. Acceptable for V1 (three known providers, simple RAG); a
  constraint only if complex multi-agent workflows emerge.
- **Runtime coupling to Spring Boot:** choosing Spring AI forecloses Quarkus for
  the AI path until/unless a re-decision (new ADR) is made.

**Re-decision triggers (would reopen Quarkus + LangChain4j):**

- an ops mandate for serverless / scale-to-zero, strict memory/density, or native
  image (GraalVM);
- a need for complex multi-agent orchestration or advanced/hybrid RAG where
  LangChain4j's granularity is decisive;
- a strategic move to a non-Spring backend runtime.

## Alternatives Considered

- **Quarkus + LangChain4j:** rejected for V1. Its main advantages (fast startup,
  low memory, native image) do not address this project's bottleneck — the pilot
  latency (`time_to_first_audio`) is dominated by STT/LLM/TTS on a pre-warmed,
  long-lived service, not JVM boot. It would add a second AI stack to the
  workspace, require CDI/Jakarta re-learning, and drop the existing Spring
  conventions/skills — cost without a V1 payoff. Strong candidate **if** an ops or
  agentic trigger above materializes.
- **LangChain4j on Spring Boot:** rejected for V1. Keeps the runtime but adds a
  non-Spring-native AI library whose observability must be integrated by hand
  (OTel is mandatory here), for granularity V1 does not need.
- **Direct provider SDK / HTTP calls, no AI framework:** rejected. Would require
  hand-building RAG, memory, streaming helpers, structured output and observability
  — exactly what a framework provides — with no V1 benefit.

## Related Documents

- `docs/architecture/adrs/ADR-0006-mistral-chat-and-ollama-embeddings.md`
- `docs/architecture/adrs/ADR-0007-source-document-knowledge-sync.md`
- `docs/architecture/adrs/ADR-0013-tokenstream-and-backend-sse-streaming-contract.md`
- `docs/architecture/adrs/ADR-0014-domain-guardrails-before-and-after-rag.md`
- `docs/architecture/adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md`
- `docs/architecture/adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md`
- `docs/architecture/adrs/ADR-0021-conversation-backend-answer-contract.md`
- `product-backlog/decisions/v1-decisions.md` (DEC-011, DEC-005)
- `product-backlog/open-questions/v1-open-questions.md` (OQ-007)
- `product-backlog/sprints/sprint-7-answer-engine.md` (TASK-BE-001)
