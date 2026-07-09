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
  vision and the target contracts are now documented, but there is still no
  production adapter, idempotency test suite, quota policy, or error strategy.
- **Non-verifiable SLOs**: the documentation states latency targets, but
  per-step observability and measured budgets remain to be implemented.
- **Documentation drift risk**: some architecture docs may lag behind the code,
  for example around `TokenStream` vs Reactor. Industrialization decisions must
  rely on code and tests, not only diagrams.

## Hard Questions

Post-review status: the voice latency question is now answered by
[`ADR-0018`](adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md). The
project uses ~700 ms as an aspirational first-audible-sentence target and
`time_to_first_audio` p95 below 800 ms as the pilot acceptance criterion.
Production SLOs remain blocked by the observability and degraded-mode gaps below.

- Resolved by ADR-0018: the pilot criterion is `time_to_first_audio` p95 below
  800 ms; ~700 ms remains an aspirational user-experience target.
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

Post-review status: `architecture.md` now documents the expected
channel/backend envelope and ADR-0019 defines the escalation handoff payload.
Implementation, idempotency tests, quotas, and degraded modes remain open before
production WhatsApp or Genesys activation.

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
| Genesys Cloud CX | Future contact-center layer | Unknown | No connector yet; `EscalationHandoff` is defined by ADR-0019. | Implement a connector only after channel contracts, observability, and degraded modes are validated. |
| WhatsApp | Future messaging channel | Unknown | Channel envelope is documented; no production adapter, idempotency tests, or async error strategy yet. | Implement only after channel contract and quota behavior are validated. |
| Mistral / Ollama | LLM generation | Good | Backend ports exist. | Add fallback, timeout, and provider error tests. |
| PostgreSQL / pgvector | Vector store and events | Moderate | pgvector remains structural in the implementation. | Keep `VectorSearchPort` and document a possible migration. |
| Redis | Active sessions | Good | Adapter exists, but failure mode must be formalized. | Add Redis failure strategy, business TTL, and controlled fallback. |

## NFR / SLA Gaps

- Pilot voice latency is now stabilized by ADR-0018, but production SLOs still
  need p99, time-to-first-token, error rate, escalation time, dashboards, and
  alerting.
- Pilot per-step budget exists in `architecture.md`, but production budget
  validation and dashboarding still need measured baselines by channel.
- No documented circuit breaker or retry strategy per provider.
- No rate limiting per channel.
- No priority policy between real-time channels and asynchronous channels.
- ADR-0019 defines the human escalation handoff contract, but no Genesys or
  equivalent connector implements it yet.
- OpenTelemetry observability and latency dashboard still in the backlog.

## Recommended Changes

### 1. Must fix before production

- Finalize production SLOs from the ADR-0018 pilot criterion: first audio p95,
  STT/TTS/LLM timeouts, error rate, and escalation time.
- Instrument metrics per step and per channel.
- Implement the human escalation connector compatible with Genesys or an
  equivalent platform.
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

---

## Addendum — V1 Billing And Genesys Handoff Challenge

Date: 2026-07-08

### Verdict

Proceed with conditions. The V1 framing is now coherent: billing invoice
explanation first, Genesys advisor handoff mandatory, full Genesys Audio
Connector routing optional. The architecture is still not ready to be treated as
V1-ready because the functional-critical paths remain contractual rather than
proven: BSS evidence, invoice PDF extraction, deterministic comparison, Genesys
handoff shape, identity, and failure modes.

### Scorecard

| Dimension | Score /5 | Rationale |
|---|---:|---|
| NFR / SLA fitness | 2 | Voice timing is defined, but comparison latency, Genesys handoff time, BSS/PDF latency, p99 and error budgets are not. |
| SLA failure modes | 1.5 | No clear customer-safe behavior is documented if Genesys, Gradium, BSS, PDF extraction, Redis, or the LLM fails during a live voice journey. |
| Modularity and boundaries | 3 | The backend/channel split is correct and Genesys is kept out of business logic, but the final channel envelope and handoff contract are still abstract. |
| External dependency replaceability | 2.5 | LLM/backend ports are acceptable; Gradium, Pipecat, Genesys, BSS, and PDF extraction replacement or fallback paths remain under-specified. |
| Evolvability and industrialization | 3 | ADRs and backlog are cleaner, but implementation evidence, runbooks, and measured gates are missing. |
| Overall | 2.4 | Solid architectural intent, fragile against real pilot constraints. |

### Critical Risks

- **Genesys is V1 scope while its mechanism is still open.** ADR-0020 makes
  Genesys advisor handoff mandatory, but OQ-006 still asks which mechanism and
  payload shape are required. This is a blocker for delivery split, not a detail.
- **The core billing value is still backlog, not system behavior.** Read-only BSS
  access, the billing domain model, invoice comparison, PDF extraction, and the
  evidence-backed explanation engine are still marked as work to do. Until these
  exist, Voice2Voice is a shell around an unproven billing engine.
- **Latency is framed too narrowly around first audio.** A quick acknowledgement
  is useful, but the functional promise depends on trustworthy invoice analysis.
  BSS retrieval, PDF extraction, deterministic comparison, and Genesys handoff
  can dominate perceived latency.
- **Escalation failure mode is undefined.** If Genesys is unavailable, rejects the
  handoff, or lacks the expected queue/context fields, the bot currently has no
  documented behavior: retry, queue, callback, ticket, fallback number, or clear
  failure statement.
- **Identity remains unresolved.** Invoice explanation cannot safely proceed
  until OQ-001 defines how phone, web voice, BSS, and Genesys context establish a
  customer identity with enough confidence.

### Hard Questions

- Which exact Genesys integration mechanism is V1: API handoff, Architect flow
  variables, queue transfer, conversation attributes, Data Action, Audio
  Connector output variables, or another pattern?
- What is the minimum handoff payload an advisor must receive on day one?
- What does the bot say and persist if Genesys handoff fails after promising a
  transfer?
- What is the maximum acceptable time from escalation trigger to Genesys queue
  entry?
- Which customer identifier is safe to pass from channel to BSS to Genesys?
- Are PDF extraction and deterministic comparison allowed to exceed the voice
  latency budget if the bot gives an acknowledgement?
- Does the pilot require phone entry through Genesys, or is Twilio acceptable for
  bot conversation while Genesys is only advisor handoff?

### Architecture Challenges

#### Genesys Handoff Mandatory, Audio Connector Optional

This is the right split, but it creates two telephony stories: Twilio/Pipecat for
bot voice and Genesys for human transfer. The handoff boundary must be explicit.
Otherwise the pilot may discover too late that a Twilio-originated session cannot
transfer cleanly into Genesys with context.

#### Backend Owns Escalation

Correct, but the backend must return more than `escalate=true`. It needs a
versioned `EscalationHandoff` contract, outcome states, retry semantics, and
auditable events.

#### Pipecat/Gradium As V1 Voice Path

Reasonable for speed, but Gradium failure must not collapse the entire product.
Text fallback, quick acknowledgement, and escalation fallback behavior need to be
explicit.

#### BSS/PDF Evidence Before LLM

Architecturally correct, but until the deterministic comparison engine exists,
"the LLM must not guess" is a policy rather than an enforceable invariant.

### External Dependency Review

| Dependency | Current role | Replaceability | Concern | Recommendation |
|---|---|---|---|---|
| Genesys Cloud CX | V1 advisor handoff | Unknown | Mandatory V1 but mechanism open. | Define handoff API/flow contract before implementation split. |
| Genesys Audio Connector | Optional full voice routing | Unknown | Could become mandatory if pilot requires Genesys entry. | Keep as spike with measured round-trip latency. |
| Twilio | Phone bot path | Moderate | May not represent the target contact-center flow. | Treat as validation fallback, not enterprise final path. |
| Gradium | STT/TTS | Hard to moderate | Voice-agent coupling and provider outage risk. | Add STT/TTS abstraction and failure tests. |
| BSS | Source of truth | Unknown | Functional success depends on availability and granularity. | Close OQ-003 before committing story estimates. |
| PDF extraction | Evidence fallback | Unknown | Partial/unusable behavior specified, reliability unknown. | Validate with fixtures before pilot. |
| Mistral/Ollama | LLM wording | Moderate | Must not invent unsupported facts. | Test prompts against missing and partial evidence cases. |
| Redis/Postgres | Session/events | Moderate | Failure behavior unclear. | Define degradation and recovery behavior. |

### NFR / SLA Gaps

- No Genesys handoff SLO: time to queue, error rate, retry count, and failure
  wording.
- No comparison SLO beyond "less than a few seconds".
- No BSS timeout budget.
- No PDF extraction timeout or confidence threshold.
- No fallback when Genesys is unavailable.
- No per-channel quota or rate limiting.
- No priority policy between real-time voice and slower async/admin flows.
- No proof that observability covers the complete path: STT -> BSS -> PDF ->
  comparison -> LLM -> TTS -> Genesys.

### Recommended Changes

#### 1. Must Fix Before Production

- Define a versioned `EscalationHandoff` contract and Genesys delivery mechanism.
- Define Genesys failure behavior and audit states.
- Define the identity and trust model for phone, web, BSS, and Genesys.
- Implement measured observability across the full billing path.

#### 2. Should Fix Before Pilot

- Add a Genesys handoff spike with a fake or sandbox endpoint.
- Add fixture tests for `parseable`, `partial`, and `unusable` invoice extraction.
- Add comparison latency measurement separate from voice latency.
- Add unavailable-provider scenarios for STT, TTS, BSS, Genesys, Redis, and LLM.

#### 3. Can Defer Safely

- Full Genesys Audio Connector voice routing.
- WhatsApp production channel.
- GPU/self-hosting.
- Advanced admin dashboard.
