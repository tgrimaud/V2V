# Backlog - Voice Support Bot

This is the technical and operational backlog. Product epics and user stories
live in [`product-backlog/`](../../product-backlog/). The canonical V1 scope is
[`docs/product/v1-scope.md`](../product/v1-scope.md).

## Classification

| Classification | Meaning |
|---|---|
| `V1 core` | Directly needed to deliver the billing/BSS invoice explanation journey |
| `V1 enabler` | Needed to deliver V1 safely, repeatedly or with enough evidence |
| `V1 pilot gate` | Needed to validate the pilot before making production-grade claims |
| `Post-MVP` | Useful after the first V1 slice |
| `Done` | Delivered in the current codebase or documentation |

## V1 Core

### B1. Read-Only BSS Billing Access

- **Classification:** V1 core
- **Status:** To do
- **Product links:** EPIC-001, EPIC-002, EPIC-003
- **Objective:** retrieve the billing periods, invoice documents, customer
  context and business events required to explain invoice deltas.
- **Constraints:** BSS is read-only, runtime access goes through typed business
  ports, and MCP/ad-hoc tools remain exploration-only.

### B0. Billing Domain Model

- **Classification:** V1 core
- **Status:** To do
- **Product links:** EPIC-001, EPIC-002, EPIC-003
- **Objective:** define the business concepts needed by the V1 explanation
  journey: invoice, invoice line, billing period, offer, option, discount, usage,
  billing event, evidence, comparison and cause.
- **Constraints:** keep monetary amounts in integer cents internally and keep the
  domain independent from BSS transport details.

### B2. Deterministic Invoice Comparison Engine

- **Classification:** V1 core
- **Status:** To do
- **Product links:** EPIC-002
- **Objective:** compare two invoices or billing periods, reconcile the global
  delta with line/cause deltas, and expose any unexplained remainder.
- **Constraints:** use integer cents internally; the LLM must not calculate
  amounts or infer unsupported causes.

### B3. Evidence-Backed Explanation Engine

- **Classification:** V1 core
- **Status:** To do
- **Product links:** EPIC-003, EPIC-008
- **Objective:** transform deterministic comparison results into a concise spoken
  explanation with evidence and explicit uncertainty.
- **Constraints:** KB content explains rules only; BSS/PDF evidence remains the
  source of factual causes and amounts.

### B4. Invoice PDF Extraction Path

- **Classification:** V1 core
- **Status:** To do
- **Product links:** EPIC-002, EPIC-003, EPIC-010, US-010
- **Objective:** extract invoice PDFs into structured evidence until a validated
  structured invoice-line endpoint exists.
- **Constraints:** product behavior must handle `parseable`, `partial` and
  `unusable` extraction states.

### V2V1. Phone And Web Voice2Voice Journeys

- **Classification:** V1 core
- **Status:** In progress
- **Product links:** EPIC-004, EPIC-005
- **Objective:** deliver oral question -> oral answer on phone and web voice.
- **Current state:** Pipecat + Gradium is the V1 target path. The custom bridge
  remains fallback/comparison only.
- **Remaining product need:** validate that billing explanations and escalation
  behave correctly on both channels.

### V2V2. Phone Telephony Validation

- **Classification:** V1 core
- **Status:** To do
- **Product links:** EPIC-004, US-012
- **Objective:** validate that the phone path can carry the same billing
  explanation and escalation behavior as the web voice path.
- **Boundary:** this validates the V1 phone journey; it does not make the custom
  bridge the target architecture.

### E1. Human Escalation Behavior

- **Classification:** V1 core
- **Status:** To do
- **Product links:** EPIC-006, ADR-0019, ADR-0020
- **Objective:** escalate on explicit advisor request or insufficient evidence,
  and provide useful context for the advisor.
- **Boundary:** the V1 target handoff is Genesys. Full Genesys voice routing is a
  separate pilot option unless the operator requires it for the first pilot.

### G1. Genesys Advisor Handoff Contract

- **Classification:** V1 core
- **Status:** To do
- **Product links:** EPIC-006, US-020, US-033, ADR-0019, ADR-0020
- **Objective:** define and validate the Genesys-compatible advisor handoff
  payload: escalation reason, customer/session identifiers allowed by the pilot
  trust model, conversation summary, compared periods, evidence, missing evidence
  and unresolved points.
- **Boundary:** this is the mandatory contact-center escalation path for V1; it
  does not require routing the entire bot call through Genesys Audio Connector.

## V1 Enablers

### M1. Contract-Compatible BSS/PDF Fixtures

- **Classification:** V1 enabler
- **Status:** To do
- **Product links:** EPIC-010, OQ-004
- **Objective:** provide realistic fixtures for nominal, expired discount,
  out-of-bundle usage, proration, insufficient data and unreliable extraction
  journeys.
- **Source:** `docs/integrations/galaxion/bss-integration-plan.md`.
- **Recommended implementation:** a planned `bss-mock/` service or equivalent
  fixture runner, not currently present in Docker Compose.

### S1. Shared Active Conversation State

- **Classification:** Done / V1 enabler
- **Status:** Done
- **Product links:** EPIC-004, EPIC-005, EPIC-006
- **Delivered:** `ConversationStore` has a Redis adapter activatable via
  `CONVERSATION_STORE=redis`, with TTL (`CONVERSATION_TTL_SECONDS`). Docker
  Compose starts Redis and configures the backend for active sessions.

### C1. Durable Conversation Events

- **Classification:** Done / V1 enabler
- **Status:** Done
- **Product links:** EPIC-006, EPIC-008, EPIC-009
- **Delivered:** `ConversationEventStore` has a JPA/Postgres adapter,
  activatable via `CONVERSATION_EVENT_STORE=jpa`, for admin history, metrics and
  audit-oriented event review.

### OM1. Channel Envelope And Escalation Handoff Contract

- **Classification:** V1 enabler
- **Status:** To do
- **Product links:** EPIC-006, EPIC-009
- **Objective:** shape the channel/backend envelope and `EscalationHandoff`
  context so phone, web voice and future channels do not duplicate business
  logic.
- **Boundary:** implement enough for V1 escalation and traceability, including
  Genesys handoff fields. WhatsApp and full Genesys Audio Connector routing remain
  separate channel integrations.

### SEC1. Billing Data Security And Audit Review

- **Classification:** V1 enabler
- **Status:** To do
- **Product links:** EPIC-008, OQ-001
- **Objective:** validate what customer/billing information may be spoken,
  displayed, logged and retained during the pilot.
- **Inputs needed:** identification level, BSS access constraints, masking rules
  and audit requirements.

## V1 Pilot Gates

### P1. Voice Latency Pilot Criterion

- **Classification:** V1 pilot gate
- **Status:** To do
- **Product links:** EPIC-009, ADR-0018
- **Objective:** verify `time_to_first_audio` p95 below 800 ms in the accepted
  pre-warmed, co-located pilot context.
- **To cover:** real streaming STT behavior, first LLM/backend response,
  first TTS audio, network time and spoken acknowledgement behavior for long BSS
  analysis.
- **Note:** the ~700 ms first-audible-sentence value remains aspirational, not a
  production SLO.

### O1. Observability For Billing Voice Journeys

- **Classification:** V1 pilot gate
- **Status:** To do
- **Product links:** EPIC-009
- **Objective:** instrument the V1 path so Product and Operations can review
  latency, escalation reasons, unresolved questions and evidence failures.
- **Minimum spans/events:** STT, BSS retrieval, invoice/PDF extraction,
  comparison, KB search, LLM first token, TTS first audio, escalation and final
  outcome.

### Q1. Evidence Quality And Escalation Review

- **Classification:** V1 pilot gate
- **Status:** To do
- **Product links:** EPIC-003, EPIC-006, EPIC-009, OQ-002
- **Objective:** review pilot conversations where the bot answered, stayed
  cautious or escalated, so the proof threshold can be tuned with Billing SME and
  Legal stakeholders.

### P2. Invoice Comparison Response Time

- **Classification:** V1 pilot gate
- **Status:** To do
- **Product links:** EPIC-002, EPIC-009, US-032
- **Objective:** measure how long BSS retrieval, invoice/PDF extraction and
  deterministic comparison take before the explanation can be trusted.
- **Boundary:** comparison speed must support conversational use, but it must not
  override evidence quality. If analysis takes longer, the voice journey should
  acknowledge quickly and wait for reliable evidence.

## Done Reference

- Inter-step streaming with backend `TokenStream` and SSE.
- Pipecat/Silero server-side VAD for the target voice path.
- Barge-in behavior in the target voice path.
- Multi-language voice support (FR + EN).
- Mistral API fallback when Ollama is too slow (`LLM_PROVIDER`).
- Multi-source KB foundation with `SourceDocument`, idempotent sync, Markdown
  connector and scheduled pull.
- Guardrails with off-topic / low-confidence behavior.
- Multi-agent routing with support / billing / sales profiles and session
  stickiness.
- Redis active sessions and JPA/Postgres durable events.

## Post-MVP Roadmap

### K1. Generic Knowledge Connectors

- **Classification:** Post-MVP
- **Status:** To do
- **Objective:** add Confluence, generic PDF and database connectors for broader
  KB enrichment.
- **Reason out of V1:** V1 invoice PDF extraction is an evidence path, not a
  generic KB connector requirement.

### F1. Enhanced Admin Dashboard

- **Classification:** Post-MVP unless needed by pilot review
- **Status:** To do
- **Objective:** richer latency charts, hourly heatmap and usage analytics.
- **V1 boundary:** pilot review needs minimum observable events; advanced
  dashboard UX can follow.

### S2. Co-Location, Kubernetes And Autoscaling

- **Classification:** Post-MVP / operator pilot hardening
- **Status:** To do
- **Objective:** deploy Pipecat agents, backend and AI services in the same
  VPC/region, with autoscaling and node separation.
- **V1 boundary:** required only when validating the ADR-0018 pilot criterion in
  an operator-like environment.

### FUT1. GPU Self-Hosting

- **Classification:** Post-MVP
- **Status:** To evaluate
- **Objective:** improve sovereignty or latency with self-hosted STT/TTS/LLM.
- **Trigger:** managed TCO, regulatory requirements or latency needs justify the
  operational cost.

### FUT2. Deeper Pipecat Consolidation

- **Classification:** Post-MVP
- **Status:** To evaluate
- **Objective:** progressively remove fallback bridge paths, unify voice channel
  handling and propagate richer real-time UI events.

### CC1. WhatsApp And Full Genesys Audio Connector Integrations

- **Classification:** Post-MVP
- **Status:** To evaluate after V1 validation, or during V1 only as a bounded
  pilot spike
- **Objective:** add asynchronous messaging and optionally route the full
  bidirectional voice conversation through Genesys Audio Connector.
- **Gate:** channel contracts, quotas, observability, idempotency, degraded modes
  and measured latency for the Genesys -> Pipecat -> Gradium -> backend -> TTS
  round trip.

### V2. Custom Brand Voice

- **Classification:** Post-MVP
- **Status:** To do
- **Objective:** configure a custom brand voice after the billing journey is
  reliable.
