# Backlog — Voice Support Bot

Tracking of remaining work. The source of truth for open items is this file; the
"Roadmap" section of `README.md` provides a condensed view.

The items come from the Roadmap and archived work plans (`~/.cursor/plans/`:
*Operator Conversation Latency*, *Voice Latency Optimizations*, *Multi-Agent
Routing POC*, *Multi-Source KB*). The statuses below have been **verified in the
code** (the plans contained obsolete statuses).

**Status legend**: `To do` · `In progress` · `Done`
**Priority legend**: 🔴 High · 🟠 Medium · 🟢 Low

---

## Private Cloud / 700 ms Target

### P1. Technical prerequisites to meet `first audio < 700 ms`
- **Priority**: 🔴 High · **Status**: To do
- **Objective**: document and implement the prerequisites needed to meet a
  `first audio < 700 ms` latency target in a private cloud.
- **To cover**: real streaming STT (**L1**), chunked/persistent streaming TTS
  (**L2**), semantic cache (**L3**), Redis shared conversational state (**S1**),
  and span-based observability (**O1**).
- **Validation criterion**: measure the latency budget per step
  (STT → retrieval → LLM first-token → TTS first-audio → network) and verify the
  SLO in a co-located and pre-warmed environment.

---

## Scalability & Omnichannel

### S1. Stateless backend + shared state (Redis)
- **Priority**: 🔴 High · **Status**: Done
- **Delivered**: `ConversationStore` has a **Redis** adapter activatable via
  `CONVERSATION_STORE=redis`, with TTL (`CONVERSATION_TTL_SECONDS`). Docker
  Compose starts Redis and configures the backend on Redis for active sessions.
- **Effect**: N backend instances can share the hot state of conversations behind
  a load balancer, instead of depending on a single-instance in-memory map.
- **Possible next step**: reuse Redis for semantic cache and short locks.

### S2. Co-location + Kubernetes / autoscaling
- **Priority**: 🟢 Low (infra) · **Status**: To do
- **Objective**: deploy bridge + backend + AI services in the same VPC/region
  (remove internet hops from the critical path), HPA on backend + bridge
  (custom "active calls" metric), separate CPU/GPU node pools, anti cold-start
  pre-warming. Depends on S1.

---

## Latency (Time To First Audio)

### L1. Real streaming STT + server-side turn detection
- **Priority**: 🟠 Medium · **Status**: To do
- **Current state**: the V1 Pipecat target (`agent/bot.py`) uses Gradium STT in
  the Pipecat pipeline with Silero server-side VAD. The legacy bridge keeps
  `stt_streaming.py` + `BatchSttSession` (REST batch) for fallback/comparison.
- **Objective**: benchmark Pipecat/Gradium streaming STT on web and telephony,
  then decide whether an alternative or self-hosted STT provider is required.

### L2. Chunked streaming TTS + persistent TTS WebSocket
- **Priority**: 🟠 Medium · **Status**: To do
- **Current state**: Pipecat uses `GradiumTTSService` in the V1 target pipeline.
  The legacy bridge keeps `gradium_tts.py`, which opens one WebSocket per
  sentence.
- **Objective**: measure Pipecat/Gradium first-audio, then optimize legacy TTS
  only if the fallback remains necessary.

### L3. Semantic cache for frequent FAQs
- **Priority**: 🟠 Medium · **Status**: To do
- **Current state**: no cache (verified — no `@Cacheable`/semantic cache).
- **Objective**: short-circuit vector search (and ideally the LLM) for very
  common questions ("my box is not working") → ~150-200 ms gain.

### L4. STT HTTP client reuse — ✅ Done
- **Priority**: 🟢 Low (quick win) · **Status**: Done
- **Delivered**: `gradium_stt.py` reuses a shared `httpx.AsyncClient`
  (`get_stt_client()`, process-wide TCP/TLS connection pool) → handshake
  eliminated between calls (~30-80 ms). Clean client shutdown is wired to bridge
  shutdown (`close_stt_client()` in `bridge_server.main()`).
- **Tests**: shared client lifecycle (reuse, closing, recreation) in
  `tests/test_gradium_stt.py`.

---

## Knowledge Base

### K1. Confluence / PDF (Tika) / database connectors
- **Priority**: 🔴 High · **Status**: To do
- **Objective**: add new connectors to the multi-source foundation to ingest
  heterogeneous documents without manual Markdown conversion.
- **Ideas**: implement `KnowledgeSourceConnector` (`sourceType()` + `fetchAll()`)
  — integration point already in place (see `../knowledge-base/knowledge-base-technical.md`).

### K2. PDF ingestion (structured extraction)
- **Priority**: 🟠 Medium · **Status**: To do
- **Objective**: structured extraction (headings, sections) to preserve hierarchy
  during chunking. Linked to K1 (PDF connector via Apache Tika).

---

## Conversation

### C1. Persistent conversational memory (JPA)
- **Priority**: 🟠 Medium · **Status**: Done
- **Delivered**: `ConversationEventStore` has a JPA/Postgres adapter,
  activatable via `CONVERSATION_EVENT_STORE=jpa`, to keep admin history and
  metrics after restart.
- **Decision**: active sessions remain in Redis (**S1**); Postgres stores durable
  events rather than hot conversational state.

---

## Observability

### O1. OpenTelemetry traces on the pipeline
- **Priority**: 🟠 Medium · **Status**: To do
- **Objective**: instrument each step (STT → vector → LLM first-token → TTS) with
  a budget per span, "first audio < 800 ms p95" SLO, dashboards + alerting.

---

## Frontend / Admin

### F1. Enhanced admin dashboard
- **Priority**: 🟢 Low · **Status**: To do
- **Objective**: pipeline latency visualizations, hourly conversation heatmap,
  usage metrics.

---

## Voice

### V1. Gradium voice cloning (brand voice)
- **Priority**: 🟢 Low · **Status**: To do
- **Objective**: custom brand voice through Gradium voice cloning.

---

## Future Improvements (Out of Current Scope)

### FUT1. GPU self-hosting (sovereignty + ultimate latency)
- Internalize the LLM (vLLM, continuous batching, first-token ~50-100 ms), then
  STT/TTS on on-prem GPU. Target ~500-600 ms and 100% internal data (secrecy of
  correspondence). GPU CAPEX + MLOps; profitable at high volume.
- The LLM layer is already abstracted (`LlmPort`/`LlmStreamingPort`); extend the
  same abstraction to STT/TTS to switch without rewriting. To be decided through
  a "self-hosting vs managed" ADR.
- **Triggers**: managed TCO > GPU TCO, regulatory requirement that data must not
  leave the environment, or need for latency < 600 ms p95 that cannot be reached
  with managed services.

### FUT2. Pipecat as a deeper real-time voice layer
- **Intent**: use Pipecat more deeply as the real-time voice orchestration
  engine, without moving business logic out of the Java backend. Pipecat must
  drive the audio path (WebRTC/Twilio → STT → backend RAG streaming → TTS →
  audio return), while the backend keeps business rules, guardrails, agent
  routing, RAG/vector search, billing, and conversational persistence.
- **Ideas**: make Pipecat the only target voice path, progressively remove the
  legacy bridge, unify WebRTC and Twilio in a Pipecat pipeline, use the barge-in
  framework, propagate RTVI/UI events (`listening`, `thinking`, `speaking`,
  current agent, citations, typed errors), and consume `/api/conversation/ask-stream`
  with end-to-end streaming.
- **Signals to report to backend/observability**: speech start/end, STT
  confidence, interruptions, silences, time-to-first-token, time-to-first-audio,
  STT/RAG/TTS latency, and barge-in rate.
- **Do not move into Pipecat**: business decisions, invoice comparison, security
  rules, persistent conversational model, and RAG logic. These responsibilities
  remain on the Java backend side to preserve the hexagonal architecture and
  testability.

---

## Done (Reference)

- [x] Inter-step streaming (sentence-by-sentence TTS during LLM generation)
- [x] Pipecat/Silero server-side VAD — natural conversation without clicking stop
- [x] Barge-in — interrupt the bot by speaking
- [x] Multi-language (FR + EN) with automatic Gradium voice selection
- [x] Mistral API fallback when Ollama is too slow (`LLM_PROVIDER`)
- [x] Multi-source KB foundation (`SourceDocument` pivot, idempotent sync,
  Markdown connector, scheduled pull)
- [x] Guardrails: "off-topic" detection with confidence score
- [x] **Multi-agent routing** (support / billing / sales): `IntentClassifier`,
  `AgentRegistry`, KB filtering by `domain`, agent stickiness, colored agent-name
  badges in the chat
- [x] **SIP/PSTN telephony**: `TwilioWebhookController`, `twilio_server.py`,
  `telephony.py`, `ulaw_8000` codec (`audio_codec.py`) — rebuilt path
- [x] Latency quick wins: sentence splitter threshold (10-12 chars + comma split),
  reduced VAD silence (500 → 300 ms)
