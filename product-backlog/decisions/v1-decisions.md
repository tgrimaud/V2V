# V1 Decision Log

This file keeps the product-readable decision summary. The authoritative
architecture decisions are the ADRs under `docs/architecture/adrs/`.

> **Two distinct "decision" numberings — do not conflate.** `DEC-001…DEC-011` below is
> the durable product decision log. The **"global-review decision #1…#9"** referenced in
> `backlog-index.md`, `done-tasks.md` and the 2026-08-15 review are a **separate,
> review-local numbering** (the items of that adversarial-review remediation loop, e.g.
> ADR-0043/0044, TASK-BE-030/031/032, TASK-WEB-032/033/034); they are **not** `DEC-###`
> entries and do not extend this log. `DEC-012`/`DEC-013` do not exist.

## DEC-001 - V1 Focuses On Invoice Explanation

**Status:** Accepted via ADR-0017  
**Date:** 2026-06-30

### Decision

V1 focuses on explaining invoice deltas for the operator's end customers.

### Rationale

The priority value is helping a customer understand why one invoice or billing
period changed compared with another. The broader telecom support assistant
remains the reusable foundation and target vision, but it must not dilute the V1
value slice.

### Implication

The V1 epics prioritize BSS evidence, deterministic invoice comparison,
evidence-backed explanation, Voice2Voice journeys and human escalation.

---

## DEC-002 - BSS Evidence Is The Source Of Truth

**Status:** Accepted via ADR-0003 and ADR-0004  
**Date:** 2026-06-30

### Decision

Read-only BSS evidence is the source of truth for invoices, contracts, offers,
options, discounts, usage, taxes, adjustments and billing events.

### Rationale

The bot must not invent amounts or causes. Deltas are calculated from evidence
first, then the LLM words the explanation.

### Implication

The LLM can reformulate and make the explanation educational, but it does not
decide causes or amounts. Runtime BSS access goes through typed business ports,
not exploration tools.

---

## DEC-003 - Invoice PDFs Are A V1 Evidence Source Until Structured Lines Are Validated

**Status:** Accepted via ADR-0005  
**Date:** 2026-07-08

### Decision

When no validated structured invoice-line endpoint exists, invoice PDFs are
extracted into deterministic JSON before comparison and explanation.

### Rationale

The V1 cannot rely on the LLM to parse invoice documents or infer line deltas.
Extraction status (`parseable`, `partial`, `unusable`) must drive product
behavior.

### Implication

The backlog includes extraction-state handling and realistic BSS/PDF fixtures.
Generic KB PDF connectors remain post-MVP; invoice PDF extraction is the V1
evidence path.

---

## DEC-004 - Voice2Voice Is Mandatory In V1

**Status:** Accepted in `docs/product/v1-scope.md`  
**Date:** 2026-06-30

### Decision

V1 must cover Voice2Voice journeys by phone and by web voice chat. Written input
is complementary.

### Rationale

The target end customer must be able to ask orally and receive an oral answer.

### Implication

Phone and web voice epics are V1 core. Web text can clarify or complement the
journey, but it does not replace Voice2Voice.

---

## DEC-005 - Gradium And Pipecat Are The Reference Voice Starting Point

**Status:** Accepted via ADR-0002, ADR-0011 and ADR-0012  
**Date:** 2026-06-30

### Decision

The V1 voice path starts with Pipecat for voice orchestration and Gradium for
STT/TTS.

### Rationale

These choices provide an operational benchmark and can be replaced behind
adapters if future testing justifies it.

### Implication

The custom bridge is fallback/comparison only. Voice provider choices must not
change the billing comparison model or the evidence contract.

---

## DEC-006 - Human Escalation Is Required

**Status:** Accepted via ADR-0019  
**Date:** 2026-06-30

### Decision

The bot escalates when the customer asks for a human advisor or when it cannot
answer safely from available evidence.

### Rationale

Reliability matters more than automation. Missing or weak proof must be visible
and actionable.

### Implication

The V1 includes explicit handoff stories, evidence-failure escalation and a
product-visible advisor context summary.

---

## DEC-007 - Java Owns Business Logic And Python Owns The Voice Edge

**Status:** Accepted via ADR-0001 and ADR-0011  
**Date:** 2026-06-30

### Decision

V1 keeps a hybrid architecture:

- Java/Spring Boot owns the conversation domain, BSS access, deterministic
  comparison, guardrails, escalation, audit and persistence.
- Python owns real-time voice orchestration, STT/TTS integration and channel
  audio handling.

### Rationale

Billing reliability, evidence rules and auditability belong in the business
backend. Real-time audio orchestration remains better suited to the voice agent.

### Implication

No V1 story should move invoice comparison, security rules or BSS reasoning into
the voice agent.

---

## DEC-008 - V1 Routing Prioritizes Billing Explanation

**Status:** Accepted via ADR-0017 and ADR-0015  
**Date:** 2026-07-08

### Decision

For V1, the product journey prioritizes billing explanation. The broader
technical, billing and sales agent registry remains a reusable support-assistant
foundation, but V1 acceptance focuses on correctly routing billing questions into
the invoice explanation journey.

### Rationale

Multi-agent routing is already useful foundation work, but presenting all support
domains as equal V1 value would dilute the billing/BSS objective.

### Implication

V1 validation must prove that billing intent reaches the billing explanation
journey and that non-billing intents are handled as foundation/fallback behavior,
not as the primary V1 success metric.

---

## DEC-009 - Genesys Handoff Is V1, Full Genesys Voice Routing Is Optional

**Status:** Accepted via ADR-0019 and ADR-0020  
**Date:** 2026-07-08

### Decision

V1 escalation targets Genesys for advisor handoff. The bot must prepare and send
a Genesys-compatible handoff context when escalation is triggered.

The full Genesys Audio Connector path, where Genesys is the entry telephony layer
and routes the complete bidirectional bot conversation to Pipecat/Gradium, is not
a mandatory V1 dependency unless the pilot environment requires it.

Genesys remains the system of record for the contact-center interaction:
ingestion, IVR/ANI context, recording, routing, queueing, supervision, agent
desktop and contact-center analytics. The backend remains the owner of AI
conversation workflow, billing reasoning, RAG, guardrails, escalation policy and
handoff content.

### Rationale

Genesys is the realistic contact-center endpoint for human escalation, so a V1
handoff without Genesys would be incomplete. Making the entire bot voice path
depend on Genesys would add integration and latency risk before the billing
explanation value is proven.

### Implication

Backlog items must separate Genesys advisor handoff from full Genesys voice
routing. The former is V1 scope; the latter is a feasibility spike or pilot
option.

---

## DEC-010 - Pilot Observability Requires Per-Step Latency Traces

**Status:** Accepted via ADR-0010 and ADR-0018
**Date:** 2026-07-09

### Decision

Pilot acceptance requires measuring the voice journey by pipeline slice before
claiming production readiness or production SLOs.

The minimum measured slices are channel ingress, end-of-turn, STT, backend first
token or action, BSS/PDF evidence retrieval, deterministic comparison, RAG/vector
search, LLM first token and completion, TTS first audio, channel egress and
Genesys handoff when applicable.

### Rationale

An end-to-end average only says that a conversation is slow. It does not show
whether the bottleneck is Genesys, the voice runtime, STT, backend orchestration,
BSS/PDF evidence, RAG, LLM, TTS or handoff.

### Implication

V1 pilot reports must use a shared correlation id and OpenTelemetry-style spans
across participating components. Reports must publish p50, p95, p99, sample
size, channel, provider configuration, warm/cold state and cache/connection
state. Genesys Analytics metrics and AI-layer metrics must be combined for pilot
review when Genesys participates in the interaction.

---

## DEC-011 - Chat LLM Provider Strategy (Mistral For Development, OpenAI For The POC)

**Status:** Accepted (user decision)
**Date:** 2026-07-17

### Decision

The answer engine's chat LLM stays behind the replaceable provider port (DEC-005).
Two providers are in scope for V1:

- **Mistral API** (`mistral-small-latest`) is the **development default** so
  implementation can progress immediately.
- **OpenAI** is the **POC target** provider. Its adapter is built to the same
  port, but **live validation is gated on OpenAI credentials**, which are not yet
  available.

Ollama remains the local/offline alternative for chat.

The **embedding** model is a **separate model** that must not be confused with the
chat LLM. It **stays Ollama `nomic-embed-text` (768 dim) as the default**, but —
like the chat LLM — it must sit behind its **own replaceable provider port /
adapter** so a different embedding provider can be swapped in easily (DEC-005).
**Caveat:** the vector dimension is fixed at `vector_store` creation, so switching
to an embedding model of a different dimension (e.g. `mistral-embed` = 1024 ≠ 768)
requires **recreating the table and re-syncing** the whole knowledge base — the
port makes the *code* swap easy, not the data migration.

### Rationale

Development must not wait for credentials, and Mistral already works. Committing
the POC to OpenAI while keeping Mistral as the working default keeps progress
unblocked, avoids any code lock-in (the port makes the switch cheap and
benchmarkable), and lets Mistral vs OpenAI be compared once the engine exists.

### Implication

- The Sprint 7 wording step (TASK-BE-005) implements provider-agnostic
  configuration supporting Mistral and OpenAI (and Ollama), selectable by config.
- The Sprint 7 ingestion step (TASK-BE-003) puts the **embedding** behind its own
  replaceable adapter (default Ollama `nomic-embed-text`, 768), config-selectable;
  a dimension change requires recreating `vector_store` + re-syncing.
- The framework decision (OQ-007 / TASK-BE-001) must support all three chat
  providers **and** a swappable embedding provider, with streaming tokens.
- OpenAI live/POC validation is deferred until credentials are provided; until
  then, functional and latency runs use Mistral (or Ollama offline).
