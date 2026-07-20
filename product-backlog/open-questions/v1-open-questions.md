# V1 Open Questions

## OQ-001 - Customer Identification By Phone And Web Voice Channel

**Status:** Open  
**Owner:** Product / BSS / Security  
**Impacts:** EPIC-001, EPIC-004, EPIC-005, EPIC-008

### Question

How is the customer identity established on each V1 channel?

### Why It Matters

The bot must explain invoices only for a customer identified with enough
confidence. The identification level determines BSS access, what can be spoken or
displayed, and when escalation is required.

### Needed Decision

- Identity source for the phone journey.
- Identity source for the web voice journey.
- Minimum confidence level for invoice access.
- Product behavior when identity is incomplete or conflicting.

---

## OQ-002 - Minimum Proof Threshold For Answering Without Escalation

**Status:** Open  
**Owner:** Product / Billing SME / Legal  
**Impacts:** EPIC-003, EPIC-006, EPIC-008

### Question

What evidence level is required for the bot to confirm a cause of invoice delta
without escalating to a human advisor?

### Why It Matters

An unproven answer may mislead the customer. A threshold that is too strict may
also create unnecessary escalations.

### Needed Decision

- Causes the bot may confirm alone.
- Causes the bot may present as probable.
- Causes that require escalation.
- Expected wording when certainty is insufficient.

---

## OQ-003 - BSS Data Availability And Granularity

**Status:** Open  
**Owner:** BSS owner  
**Impacts:** EPIC-001, EPIC-002, EPIC-003, EPIC-010

### Question

Which BSS data is available in read-only mode to explain invoice deltas?

### Why It Matters

The comparison engine and customer-visible evidence depend directly on available
granularity: invoice lines, usage, discounts, prorations, options, taxes, billing
events and offer changes.

### Needed Decision

- Data accessible in V1.
- Available history depth.
- Expected freshness.
- Access and confidentiality limits.
- Whether any structured invoice-line endpoint can replace PDF extraction later.

---

## OQ-004 - Invoice PDF Extraction Reliability And Fixture Coverage

**Status:** Open  
**Owner:** Product / BSS / QA  
**Impacts:** EPIC-002, EPIC-003, EPIC-010

### Question

Which real invoice PDFs and extraction quality thresholds are required to validate
the V1 explanation behavior?

### Why It Matters

ADR-0005 makes invoice PDF extraction the V1 evidence path until a validated
structured line endpoint exists. Product behavior depends on whether extraction
is `parseable`, `partial` or `unusable`.

### Needed Decision

- Minimum anonymized PDF samples for pilot validation.
- Required fixture journeys: nominal, discount expiry, overage, proration,
  insufficient data, partial/unusable extraction.
- Acceptance threshold for treating extracted lines as confirmed evidence.
- Expected customer wording for partial or unusable extraction.

---

## OQ-005 - Pilot Latency Acceptance Context

**Status:** ✅ Decided (2026-07-20) — resolved by
[ADR-0029](../../docs/architecture/adrs/ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md).
The stub-era `p95 < 800 ms` is revised for the real-backend Gradium cascade to a
**mouth-to-ear p95 ≤ 1.5 s** primary criterion (market production-viability ceiling)
and a **`time_to_first_audio` p95 ≤ 1.2 s** engineering sub-target; ~700 ms stays an
aspirational experience target reachable only via speech-to-speech. Prerequisite to
sign-off: instrument true mouth-to-ear (`channel_egress` + end-of-turn hold,
**TASK-WEB-009**). STT/TTS are at the Gradium floor, so the latency lever is the
answer engine and the criterion — not the voice edges; ADR-0012 (modular cascade) is
reaffirmed and "OpenAI" for V1 means the cascade chat provider (ADR-0006/DEC-011),
not Realtime speech-to-speech. Remaining OQ-005 sub-items (journeys counted,
fixture-vs-live provider mix, barge-in authority) fold into TASK-WEB-009 and the QA
latency plan.

**Owner:** Product / Architecture / Operations  
**Impacts:** EPIC-004, EPIC-005, EPIC-009

### Question

Under which measured conditions is the V1 voice journey accepted for the pilot?

### Why It Matters

ADR-0018 defines `time_to_first_audio` p95 below 800 ms as a pilot criterion in a
pre-warmed, co-located environment, not a production SLO. The backlog must avoid
turning an aspirational target into an unmeasured contractual promise.

### Needed Decision

- Measurement environment and sample size.
- Which journeys count toward the pilot metric.
- Which latency slices must be reported separately: channel ingress,
  end-of-turn, STT, backend first token, BSS/PDF evidence, comparison, RAG,
  LLM, TTS first audio, channel egress, and Genesys handoff.
- Which tests use controlled fixtures, fake providers, sandbox providers, or
  real provider calls.
- Warm and cold conditions: cache state, pre-opened TTS connection, pre-warmed
  LLM, preloaded vector index, and co-location assumptions.
- How long-running BSS evidence analysis is handled with a quick spoken
  acknowledgement.
- What latency or evidence failures require degraded mode or escalation.
- How barge-in is measured and which component is authoritative for cancelling
  playback or interrupting an in-flight turn.

---

## OQ-006 - Genesys Handoff Integration Shape

**Status:** Open  
**Owner:** Product / Contact Center / Architecture / Security  
**Impacts:** EPIC-006, EPIC-008, EPIC-009

### Question

Which Genesys mechanism and payload shape are required for V1 advisor handoff?

### Why It Matters

Genesys is the V1 escalation target, but the product must distinguish mandatory
advisor handoff from optional full Audio Connector voice routing. The handoff
contract determines what context can be sent to the advisor and what security
constraints apply.

### Needed Decision

- Genesys handoff mechanism for the pilot.
- Required and allowed handoff fields.
- Customer/session identifiers allowed by the pilot trust model.
- Queue or skill routing rules for billing advisor escalation.
- Whether full Genesys Audio Connector routing is required for the pilot or only
  a feasibility spike.
- Whether Genesys is the phone entry point for pilot calls or only the advisor
  handoff target.
- If full Genesys voice routing is used, which media integration is selected
  (AudioHook, Audio Connector, SIP, or another approved pattern).
- Which Genesys attributes, task variables, or Open API objects carry transcript
  summary, detected intent, escalation reason, BSS evidence, and unresolved
  points to the advisor desktop.
- Which Genesys Analytics metrics and AI-layer metrics are combined in the pilot
  KPI dashboard.

---

## OQ-007 - Backend AI/RAG Framework (Spring AI vs LangChain4J vs Other)

**Status:** ✅ Decided (2026-07-17) — **Spring Boot + Spring AI** for V1, recorded in
[ADR-0026](../../docs/architecture/adrs/ADR-0026-backend-runtime-and-ai-framework.md).
Quarkus + LangChain4j deliberately deferred (reconsidered only on an ops/native-image
or complex-agentic trigger). Providers stay behind replaceable ports (DEC-005, DEC-011,
ADR-0006). TASK-BE-001 (Sprint 7) implements the recorded decision.
**Owner:** Architecture / Backend
**Impacts:** EPIC-005, EPIC-006 (TASK-WEB-003-C HTTP backend adapter and the future
Java answer engine that implements the conversation contract), EPIC-002/003/004

### Question

Which framework does the Java backend use to build the answer engine (LLM
orchestration, RAG, tool/function calling, provider abstraction): **Spring AI**,
**LangChain4J**, or another option?

### Why It Matters

The Sprint 5 backend bridge is deliberately **contract-first**: the voice runtime
talks to a `BackendAnswerPort` with a stub adapter (default) and an HTTP adapter,
so **Sprint 5 does not require this decision**. But the real answer engine behind the
HTTP contract does. The choice affects provider replaceability (DEC-005: LLM/STT/TTS
must stay swappable behind ports), RAG/pgvector integration, guardrails, streaming
support, observability hooks (DEC-010) and team familiarity.

### Needed Decision

- Framework for LLM orchestration + RAG in the Java backend.
- How it preserves the provider-agnostic port/adapter boundary (Mistral API default,
  Ollama alternative for chat; Ollama `nomic-embed-text` for embeddings).
- Streaming-token support for the low-latency voice loop (feeds Sprint 6).
- Whether the decision warrants an ADR under `docs/architecture/adrs/`.

### Notes

- Deferred by the user until after Sprint 5 planning; **must not be forgotten** — to
  be discussed before the Java answer engine (HTTP backend behind TASK-WEB-003-C)
  is implemented.
