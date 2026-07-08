# Adversarial Architecture Review — Omnichannel Vision

Date: 2026-07-08

## Verdict

The overall direction is sound: independent channels, a shared Java backend for
business logic, and Genesys Cloud CX and WhatsApp positioned as adapters rather
than business engines.

However, the solution should not yet be presented as an industrialized
omnichannel platform. At this stage, it is closer to a **solid POC with a
coherent industrialization vision**. The weak points are mainly NFRs/SLAs,
degraded modes, observability, and integration contracts between channels and
the backend.

## Scorecard

| Dimension | Score /5 | Rationale |
|---|---:|---|
| NFR / SLA fitness | 2 | The latency target exists, but prerequisites such as STT streaming, chunked TTS, semantic cache, and observability remain in the backlog. |
| SLA failure modes | 2 | Timeouts exist, but retry, circuit breaker, rate limiting, and explicit degraded modes per channel are missing. |
| Modularity and boundaries | 3.5 | The Java backend is well structured around ports/adapters; on the voice-agent side, Gradium/Twilio are still very present directly in the pipelines. |
| External dependency replaceability | 2.5 | LLM and persistence are relatively replaceable. STT/TTS, Twilio, Genesys, and WhatsApp still need to be formalized as adapters/ports. |
| Evolvability and industrialization | 3 | The omnichannel vision is correct, but stable contracts and evidence of operational isolation are missing. |
| Overall | 2.8 | Good MVP foundation, not yet a robust production target. |

## Critical Risks

- **Java backend as a concentration point**: all channels converge toward the
  same conversation engine. This is desirable for business consistency, but
  dangerous without rate limiting, timeouts, metrics, and quotas per channel.
- **Gradium coupling in the voice-agent**: `GradiumSTTService` and
  `GradiumTTSService` are instantiated directly in the Python pipelines.
  Replacing Gradium will require more than a simple new adapter.
- **Genesys/WhatsApp still conceptual**: they are correctly positioned in the
  vision, but there is no integration contract, escalation payload,
  conversation mapping, idempotency, or error strategy yet.
- **Non-verifiable SLOs**: the documentation states latency targets, but
  per-step observability and measured budgets remain to be implemented.
- **Documentation drift risk**: some architecture docs may lag behind the code,
  for example around `TokenStream` vs Reactor. Industrialization decisions must
  rely on code and tests, not only diagrams.

## Hard Questions

- Which official SLO must be met: first audio p95 below 700 ms, 800 ms, or
  1 second?
- What happens if Gradium STT is slow but text channels are working?
- What happens if Genesys Cloud CX is unavailable at the moment of escalation?
- Can a channel be disabled, restarted, or deployed without redeploying the
  Java backend?
- Which single contract should channels call: `ask`, `ask-stream`, or a future
  channel-oriented conversation API?
- How do we prevent a WhatsApp flood from degrading real-time voice?

## Architecture Challenges

### Shared Java Backend

The choice is good because it centralizes RAG, guardrails, multi-agent routing,
escalation, and persistence. But it must now be treated as an **internal product
consumed by multiple channels**, with contracts, versioning, timeouts, quotas,
and observability.

### Independent Channels

The vision is correct, but it must be translated into stable objects and
contracts: `channel`, `conversation_id`, `external_session_id`, `message_id`,
`idempotency_key`, `reply_mode`, `escalation_context`.

### Pipecat as the Voice Target

Pipecat is a credible choice for real-time voice. However, the project must
explicitly decide whether the legacy bridge remains a maintained fallback or a
path to remove. Keeping two complete voice paths increases testing cost and the
risk of divergence.

### Genesys Cloud CX

Genesys must remain a contact-center layer: channels, queues, agent desktop,
supervision, and human handoff. It must not own RAG, business rules, escalation,
or conversation memory.

## External Dependency Review

| Dependency | Current role | Replaceability | Concern | Recommendation |
|---|---|---|---|---|
| Gradium STT/TTS | Transcription and speech synthesis | Hard | Direct coupling in the Python pipelines. | Introduce an STT/TTS provider abstraction on the voice-agent side. |
| Twilio | Telephony / Media Streams | Moderate | The protocol is partially isolated but remains tied to the telephony flow. | Keep Twilio as a channel adapter and define an internal telephony contract. |
| Genesys Cloud CX | Future contact-center layer | Unknown | No connector or escalation payload yet. | Define an `EscalationHandoff` contract. |
| WhatsApp | Future messaging channel | Unknown | No adapter or async contract yet. | Create a messaging contract with idempotency. |
| Mistral / Ollama | LLM generation | Good | Backend ports exist. | Add fallback, timeout, and provider error tests. |
| PostgreSQL / pgvector | Vector store and events | Moderate | pgvector remains structural in the implementation. | Keep `VectorSearchPort` and document a possible migration. |
| Redis | Active sessions | Good | Adapter exists, but failure mode must be formalized. | Add Redis failure strategy, business TTL, and controlled fallback. |

## NFR / SLA Gaps

- SLOs are not stabilized: p95/p99, time-to-first-audio,
  time-to-first-token, error rate, escalation time.
- No clear per-step budget: STT, RAG, vector search, LLM, TTS, network.
- No documented circuit breaker or retry strategy per provider.
- No rate limiting per channel.
- No priority policy between real-time channels and asynchronous channels.
- No human escalation contract usable by Genesys or an equivalent platform.
- OpenTelemetry observability and latency dashboard still in the backlog.

## Recommended Changes

### 1. Must fix before production

- Define measurable SLOs: first audio p95, STT/TTS/LLM timeouts, error rate,
  escalation time.
- Instrument metrics per step and per channel.
- Define the human escalation contract compatible with Genesys or an equivalent
  platform.
- Add timeouts, quotas, and rate limiting per channel.

### 2. Should fix before pilot

- Introduce an STT/TTS abstraction on the Python side.
- Define a stable channel API for WhatsApp, web chat, and telephony.
- Formalize the `channel`, `external_session_id`, `message_id`, and
  `idempotency_key` fields.
- Add failure tests: unavailable STT/TTS provider, slow backend, unavailable
  Redis, duplicate message, impossible escalation.

### 3. Can defer safely

- Real Genesys Cloud CX connector.
- Real WhatsApp channel.
- STT/TTS/LLM self-hosting.
- Advanced admin dashboard.

## Decision to Retain

The target to prioritize is: **independent entry points per channel + shared
Java backend for business logic**.

This target maximizes evolvability and limits cross-impact, but it only becomes
robust once channel/backend contracts, SLOs, and degraded modes are explicitly
defined and tested.
