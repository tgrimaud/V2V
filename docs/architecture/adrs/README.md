# Architecture Decision Records

This folder contains Architecture Decision Records (ADRs) for Voice Support Bot.

ADRs capture structural decisions that should remain visible beyond code, chats,
diagrams, and planning notes. When a decision changes, create a new ADR and mark
the previous one as superseded instead of rewriting history.

> **Note:** an ADR status of `Accepted` records an accepted **target decision**,
> not that the decision is implemented on this branch. On `feat/restart-from-scratch`
> only the STT-validation slice is built; implementation status is tracked in
> `product-backlog/` and `docs/operations/backlog.md`.

## Index

| ADR | Status | Decision |
|---|---|---|
| [ADR-0001](ADR-0001-java-backend-owns-conversation-domain.md) | Accepted | Java backend owns conversation, RAG, guardrails, routing, escalation, and persistence. |
| [ADR-0002](ADR-0002-pipecat-gradium-target-voice-path.md) | Accepted | Pipecat + Gradium is the target V1 voice path; custom bridge remains legacy/fallback. |
| [ADR-0003](ADR-0003-billing-v1-uses-read-only-bss-and-deterministic-comparison.md) | Accepted | Billing V1 uses read-only BSS data and deterministic invoice comparison before LLM wording. |
| [ADR-0004](ADR-0004-bss-integration-through-typed-domain-ports.md) | Accepted | BSS access goes through typed domain ports and contract-compatible adapters, not runtime MCP. |
| [ADR-0005](ADR-0005-invoice-pdf-extraction-before-llm-explanation.md) | Accepted | Invoice PDFs are extracted into deterministic JSON before comparison and explanation. |
| [ADR-0006](ADR-0006-mistral-chat-and-ollama-embeddings.md) | Accepted | Mistral is the default chat LLM; Ollama `nomic-embed-text` remains the embedding model. |
| [ADR-0007](ADR-0007-source-document-knowledge-sync.md) | Accepted | Knowledge ingestion uses a source-agnostic `SourceDocument` pivot and idempotent sync. |
| [ADR-0008](ADR-0008-redis-active-sessions-postgres-durable-events.md) | Accepted | Redis stores active conversation state; PostgreSQL stores durable events and vector data. |
| [ADR-0009](ADR-0009-independent-channel-adapters-shared-java-backend.md) | Accepted | Omnichannel entry points stay independent while sharing the Java conversation backend. |
| [ADR-0010](ADR-0010-industrialization-requires-contracts-slos-and-observability.md) | Accepted | Industrialization requires channel contracts, escalation contract, measurable SLOs, and observability before adding real channels. |
| [ADR-0011](ADR-0011-voice-channels-through-pipecat-text-channels-to-backend.md) | Accepted | Voice channels go through channel proxies to Pipecat; text channels go directly to the Java backend. |
| [ADR-0012](ADR-0012-modular-voice-pipeline-over-realtime-api.md) | Accepted | Voice support uses a modular STT/RAG/LLM/TTS pipeline instead of an all-in-one realtime provider. |
| [ADR-0013](ADR-0013-tokenstream-and-backend-sse-streaming-contract.md) | Accepted | Backend streaming uses the domain `TokenStream` contract and SSE at the API boundary. |
| [ADR-0014](ADR-0014-domain-guardrails-before-and-after-rag.md) | Accepted | Guardrails run in the backend domain pipeline before and after retrieval. |
| [ADR-0015](ADR-0015-keyword-routing-with-session-stickiness.md) | Accepted | Multi-agent routing uses deterministic keyword scoring with session stickiness. |
| [ADR-0016](ADR-0016-legacy-bridge-is-fallback-and-comparison-path.md) | Accepted | The custom bridge remains a legacy fallback and comparison path, not the V1 target. |
| [ADR-0017](ADR-0017-billing-v1-with-general-support-foundation.md) | Accepted | Billing invoice explanation is the V1 value focus on top of the general support assistant foundation. |
| [ADR-0018](ADR-0018-voice-latency-targets-and-slo-measurement.md) | Accepted | Voice latency uses a shared taxonomy: ~700 ms experience target, p95 < 800 ms pilot criterion, production SLO deferred until observability gates are met. |
| [ADR-0019](ADR-0019-escalation-rules-and-handoff-contract.md) | Accepted | Escalation decisions stay in the backend and future contact-center handoff uses a shared payload. |
| [ADR-0020](ADR-0020-genesys-handoff-v1-full-audio-connector-optional.md) | Accepted | Genesys advisor handoff is V1 scope; full Genesys Audio Connector routing remains optional unless the pilot requires it. |
| [ADR-0021](ADR-0021-conversation-backend-answer-contract.md) | Accepted | The voice runtime talks to the conversation backend through a neutral `BackendAnswerPort` answer contract (stub + HTTP adapters), keeping providers replaceable. |
