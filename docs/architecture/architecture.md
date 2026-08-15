# Architecture — Voice Support Bot

> Restart branch note: on `feat/restart-from-scratch`, the previous implementation
> was first removed, then rebuilt from scratch. **Some sections below still describe
> the full TARGET architecture** (billing/BSS, Genesys, telephony, Redis, React
> frontend) that is **not yet built** — present-tense wording in those sections
> refers to design intent and to the `main` reference implementation. Read the
> "What is actually built on this branch today" block below for the current state.
>
> **What is actually built on this branch today (through Sprint 11)** is a full
> **web Voice2Voice loop** across two rebuilt services, now packaged for deployment:
>
> - **Python voice runtime** (`voice-agent/`, port `8090`): **STT**
>   (`stt_validation/` — fixture + real Gradium, batch REST **and** streaming
>   WebSocket), **TTS** (`tts_synthesis/` — fixture + real Gradium, batch **and**
>   streaming), a neutral **answer seam** (`conversation_backend/` —
>   `BackendAnswerPort` with a `stub` default and an `http` adapter to the Java
>   backend, plus a safe degraded-mode fallback), the HTTP server (`web_voice/`) +
>   batch pipeline (`voice_pipeline/`). Both the **batch** loop
>   (`POST /api/voice/turn`) and the **streaming WebRTC** loop
>   (`POST /api/voice/webrtc/offer`) run end to end, with energy-based end-of-turn
>   detection and native **barge-in** (Sprints 6–8). Runs through a **Pipecat**
>   pipeline by default (`--runtime {stdlib,pipecat}`, `--provider {fixture,gradium}`,
>   `--backend {stub,http}`). Neutral `voice_common/` holds telemetry, sanitization
>   and per-slice timing; STT and TTS halves never import each other (architecture test).
> - **Java conversation backend** (`backend/`, port `8080`): hexagonal Spring Boot
>   app with **RAG** over **pgvector** (Ollama `nomic-embed-text`, 768-dim, domain +
>   audience filters), input/output **guardrails** (incl. DEC-002 no-fabricated-amount),
>   three-band retrieval **confidence**, conversation **memory**, and per-slice
>   correlation-id observability. Chat = **Mistral** (default), embeddings = **Ollama**.
>   Endpoints: `POST /api/conversation/{converse,converse-stream,answer,retrieve,warm-up}`,
>   `POST /api/knowledge/{ingest,sync}`, OpenAPI/Swagger UI.
> - **Infra:** local `docker-compose.yml` (Postgres/`pgvector` on 5433 + Ollama) for
>   dev, **plus the Sprint 11 deployment packaging**: Docker images for both services,
>   `deploy/compose/` stacks per tier, HAProxy/Keepalived VIPs, GitHub Actions CI, and
>   an Ansible deploy (packaged/deployable, not yet live on tst — network-access open
>   inputs). **Redis-backed shared conversation memory** is built (`CONVERSATION_STORE=redis`,
>   TASK-BE-021) so two backends behind a VIP keep multi-turn context.
>
> **Not built yet** (target only): customer identity, read-only BSS access, invoice
> PDF extraction + deterministic comparison, escalation contract + Genesys handoff,
> phone (Twilio) Voice2Voice, and the standalone React frontend (the web client is the
> `web_voice/` static page). Route/port tables further down this document may still
> show the legacy `main` contract (`/api/conversation/ask`, `ask-stream`, `:8081`,
> `agent/bot.py`, `:7860` Pipecat UI, `:5173` React); the authoritative current
> contract is the one in this block. See `voice-agent/README.md` and
> `product-backlog/backlog-index.md`.

## Overview

Voice Support Bot is an intelligent voice agent that answers customer support
questions in the Telecom/ISP domain. It uses the **RAG**
(Retrieval-Augmented Generation) pattern to provide factual answers based on an
internal knowledge base.

The architecture is **hybrid**:
- A **Java backend** (hexagonal) handles business logic, RAG, and administration
- A **Python Pipecat voice agent** orchestrates the real-time audio pipeline with Gradium (STT/TTS)
- A **Pipecat WebRTC** channel serves the target V1 web journey, with Twilio Media Streams for telephony
- **Genesys Cloud CX** is the target contact-center system of record for call
  ingestion, compliance recording, queueing, supervision, reporting, and human
  advisor handoff
- The **React frontend + custom WebSocket bridge** existed on `main` as a historical POC / fallback (removed on this branch); it is no longer the target V1 path

The machine/VM target for an operator V1 pilot is detailed in
[`infra-v1.md`](infra-v1.md). The BSS integration plan and contract-compatible
mock are detailed in
[`bss-integration-plan.md`](../integrations/galaxion/bss-integration-plan.md).
Structuring decisions are tracked as ADRs in
[`adrs/`](adrs/).

Key decisions referenced by this architecture spine include
[ADR-0002](adrs/ADR-0002-pipecat-gradium-target-voice-path.md) for the target
voice path,
[ADR-0008](adrs/ADR-0008-redis-active-sessions-postgres-durable-events.md) for
conversation persistence,
[ADR-0009](adrs/ADR-0009-independent-channel-adapters-shared-java-backend.md) for
omnichannel boundaries,
[ADR-0010](adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md)
for production gates,
[ADR-0011](adrs/ADR-0011-voice-channels-through-pipecat-text-channels-to-backend.md)
for voice/text channel routing,
[ADR-0018](adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md) for
latency targets, and
[ADR-0019](adrs/ADR-0019-escalation-rules-and-handoff-contract.md) for escalation
handoff, and
[ADR-0020](adrs/ADR-0020-genesys-handoff-v1-full-audio-connector-optional.md)
for the Genesys handoff and full voice-routing boundary.

## Architecture Diagram

```mermaid
graph TB
    %% ─── Clients ───
    Browser["👤 Browser"]
    Twilio["👤 Twilio"]

    %% ─── Our code: Frontend / UI ───
    subgraph frontend ["🟢 Web UI"]
        PipecatUI[Pipecat prebuilt UI WebRTC :7860]
        VoiceChat[React VoiceChat legacy :5173]
    end

    %% ─── Our code: Voice Agent ───
    subgraph voiceAgent ["🟢 Voice Agent — Python"]
        PipecatBot[agent/bot.py Pipecat pipeline]
        StreamingRAG[streaming_rag_processor.py]
        BridgeServer[bridge_server.py legacy fallback]
        BackendClient[backend_client.py]
    end

    %% ─── External: Gradium (near the voice agent that calls it) ───
    subgraph gradium ["🔴 Gradium Cloud API"]
        GradiumSTT[STT — api.gradium.ai]
        GradiumTTS[TTS — wss://api.gradium.ai]
    end

    %% ─── Our code: Java Backend ───
    subgraph backend ["🟢 Java Backend — Spring Boot"]
        subgraph adaptersIn [Adapters IN]
            ConvController[ConversationController]
            StreamController[StreamingConversationController]
        end
        subgraph domain [Domain]
            Orchestrator[ConversationOrchestrator]
            IntentClass[IntentClassifier]
            AgentReg[AgentRegistry]
            EscDetector[EscalationDetector]
            RAGPipeline["RAG Pipeline"]
        end
        subgraph adaptersOut [Adapters OUT]
            MistralAdapter[MistralLlmAdapter]
            OllamaAdapter[OllamaLlmAdapter]
            PgVecAdapter[PgVectorStoreAdapter]
        end
    end

    %% ─── External: LLM + DB (near the backend that calls them) ───
    MistralAPI["🔴 Mistral AI Cloud"]
    Ollama["🔴 Ollama Local :11434"]
    PgVector["🔴 PostgreSQL + pgvector :5433"]

    %% ─── Inbound flows ───
    Browser -->|"WebRTC :7860"| PipecatUI
    PipecatUI --> PipecatBot
    Twilio -->|"Media Streams"| PipecatBot
    Browser -.->|"legacy ws:8765"| VoiceChat
    VoiceChat -.->|"legacy PCM + JSON"| BridgeServer

    %% ─── Voice Agent → Gradium (external) ───
    PipecatBot -->|"GradiumSTTService streaming"| GradiumSTT
    BridgeServer -.->|"legacy HTTPS POST"| GradiumSTT

    %% ─── Voice Agent → Backend (internal) ───
    PipecatBot --> StreamingRAG
    StreamingRAG --> BackendClient
    BridgeServer -.-> BackendClient
    BackendClient -->|"GET SSE /ask-stream"| StreamController

    %% ─── Internal backend ───
    StreamController --> Orchestrator
    Orchestrator --> IntentClass
    IntentClass --> AgentReg
    Orchestrator --> EscDetector
    Orchestrator --> RAGPipeline
    ConvController --> Orchestrator

    %% ─── RAG pipeline → Adapters ───
    RAGPipeline --> PgVecAdapter
    RAGPipeline --> MistralAdapter
    RAGPipeline --> OllamaAdapter

    %% ─── Voice Agent → TTS (external) ───
    PipecatBot -->|"GradiumTTSService streaming"| GradiumTTS
    BridgeServer -.->|"legacy WSS"| GradiumTTS

    %% ─── Backend → External services ───
    MistralAdapter -->|"generation HTTPS streaming"| MistralAPI
    OllamaAdapter -->|"generation HTTP streaming"| Ollama
    PgVecAdapter -->|"retrieval SQL + HNSW"| PgVector
```

> **Legend**: 🟢 = our code · 🔴 = external service

## Outbound Flows

The system calls the following external services:

| Flow | Protocol | Source → Destination | Content |
|------|-----------|---------------------|---------|
| **LLM Generation** | HTTPS (streaming) | `MistralLlmAdapter` → Mistral API | Prompt + RAG context → streamed tokens |
| **LLM Generation (alt)** | HTTP (streaming) | `OllamaLlmAdapter` → Ollama local :11434 | Prompt + context → streamed tokens |
| **Vector Search** | SQL (TCP :5433) | `PgVectorStoreAdapter` → PostgreSQL/pgvector | Query embedding → top-K HNSW chunks |
| **Embedding Generation** | HTTP | Spring AI → Ollama (nomic-embed-text) | Text → 768-dimensional vector |
| **STT Transcription** | Pipecat service / HTTPS | `agent/bot.py` → Gradium STT | WebRTC/Twilio audio → transcription |
| **TTS Synthesis** | Pipecat service / WSS | `agent/bot.py` → Gradium TTS | Text → audio stream |
| **RAG Query (streaming)** | HTTP SSE | `streaming_rag_processor.py` → Backend :8081 `/api/conversation/ask-stream` | Question → SSE token stream |
| **RAG Query (legacy fallback)** | HTTP POST | `bridge_server.py` → Backend :8081 `/api/conversation/ask` | Question → JSON response |
| **Greeting seed** | HTTP POST | `bot.py` → Backend :8081 `/api/conversation/seed` | Pipecat greeting stored in history to avoid greeting again |

## Responsibility Split

| Component | Language | Responsibility |
|-----------|---------|---------------|
| **Pipecat Web UI** | TypeScript / prebuilt | Target V1 WebRTC interface for the web voice journey |
| **Frontend React legacy** | TypeScript | WebSocket POC interface, browser VAD, audio queue playback, text streaming |
| **Voice Agent Pipecat** | Python | WebRTC/Twilio audio orchestration, STT/TTS via Gradium, server VAD, barge-in framework |
| **Custom legacy bridge** | Python | WebSocket POC/fallback path, Gradium STT/TTS, sentence splitting, SSE consumer |
| **Gradium** | Cloud API | STT (transcription) and TTS (speech synthesis) |
| **Backend Java** | Java (Spring Boot) | RAG, LLM streaming (SSE), business logic, escalation, admin |
| **Mistral AI** | Cloud API | LLM generation (default provider, streaming) |
| **Ollama** | Local | Local LLM inference (configurable alternative) |
| **PostgreSQL + pgvector** | — | Vector storage and similarity search |

## Channel / Backend Contract

[ADR-0009](adrs/ADR-0009-independent-channel-adapters-shared-java-backend.md),
[ADR-0010](adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md),
[ADR-0011](adrs/ADR-0011-voice-channels-through-pipecat-text-channels-to-backend.md),
and [ADR-0019](adrs/ADR-0019-escalation-rules-and-handoff-contract.md) define
the omnichannel boundary: channels are adapters, while the Java backend owns
conversation behavior, guardrails, billing reasoning, routing, escalation, and
memory.

### Current MVP Routes

The current routes are sufficient for the V1 web/Pipecat MVP:

| Route | Current use | Contract status |
|---|---|---|
| `POST /api/conversation/ask` | Synchronous text answer and legacy bridge fallback | MVP route, not the final omnichannel envelope |
| `GET /api/conversation/ask-stream` | Backend SSE stream consumed by Pipecat and text clients | MVP streaming route, not the final omnichannel envelope |
| `POST /api/conversation/seed` | Store the Pipecat greeting in backend history | Voice-runtime support route |

Before production WhatsApp, Genesys, or equivalent channel integrations, channel
adapters must normalize an envelope containing:

| Field | Purpose |
|---|---|
| `channel` | Source channel such as `web_voice`, `phone`, `web_chat`, `whatsapp_text`, `whatsapp_voice`, `contact_center_chat`, or `genesys_voice` |
| `conversation_id` | Internal backend conversation id |
| `external_session_id` | Channel/provider session id, e.g. Twilio call SID, WhatsApp thread id, or Genesys conversation id |
| `message_id` | Channel/provider inbound message or event id |
| `idempotency_key` | Duplicate protection for retries and asynchronous delivery |
| `reply_mode` | Expected response mode: `sync`, `stream`, `async`, or `handoff` |
| `customer_reference` | Optional safe customer/account reference resolved by the channel adapter, Genesys IVR/ANI lookup, or the BSS trust model |
| `escalation_context` | Optional handoff context following [ADR-0019](adrs/ADR-0019-escalation-rules-and-handoff-contract.md) |

Current `ask` and `ask-stream` calls may keep accepting `question` and
`conversation_id` for the MVP. A future channel-oriented API or compatibility
adapter must add the envelope above before production-grade asynchronous
channels. This keeps WhatsApp and Genesys integration from duplicating business
logic or hiding idempotency and escalation behavior inside channel code.

### Channel Roles

| Channel / Layer | Status | Responsibility |
|---|---|---|
| Pipecat WebRTC | Target V1 voice path | Real-time web voice transport through Pipecat |
| Twilio Media Streams | Target telephony voice path | Phone audio transport through Pipecat |
| Web chat text | MVP/direct text path | Calls the Java backend directly |
| WhatsApp text | Future async channel adapter | Calls the Java backend with the channel envelope; not production before contract, SLO, quotas, and observability are ready |
| WhatsApp voice/call | Future voice channel adapter | Goes through a WhatsApp voice proxy to Pipecat |
| Genesys Cloud CX | Target contact-center system of record | Owns call ingestion, IVR/ANI context, compliance recording, routing, queues, agent desktop, supervision, reporting, and human handoff; does not own RAG, billing reasoning, guardrails, or memory |

### Target Genesys Contact-Center Pattern

The target enterprise call path keeps Genesys Cloud CX as the system of record
for the contact-center interaction. Genesys ingests the call, applies the
operator's IVR and identification rules, records and supervises the interaction,
then routes eligible calls to a virtual-agent queue or flow.

For a full voice-routing pilot, Genesys streams audio to the voice runtime
through AudioHook or the selected Genesys media integration. The voice runtime
handles STT/TTS or speech-to-speech, barge-in, and low-latency audio orchestration,
then calls the Java backend through the normalized channel envelope. The Java
backend remains the owner of conversation policy, RAG, billing evidence retrieval,
guardrails, multi-agent routing, escalation decisions, and audit events.

When escalation is required, the backend prepares a versioned
`EscalationHandoff` and a Genesys adapter attaches the permitted context to the
Genesys interaction before transferring it to the normal advisor queue. The
handoff context must include the escalation reason, transcript summary, detected
intent, customer/session identifiers allowed by the trust model, evidence already
collected, unresolved points, and recommended next advisor action. The advisor
must receive enough context to continue the conversation without asking the
customer to restart from zero.

Authentication and customer identification should happen before or as the AI
conversation starts. The target path reuses Genesys IVR, ANI, or existing
contact-center lookup data when available instead of duplicating identity logic
inside the voice runtime. The backend may still enforce its own BSS access rules
from the identity confidence and customer reference it receives.

## Domain Layer (Pure Java)

The domain contains **no Spring annotations**. It is testable with simple fakes.

LLM streaming also remains expressed in the domain language through
`TokenStream`. Spring AI/Reactor adapters convert their technical streams to
this abstraction before returning to the domain.

### Models

| Class | Role |
|--------|------|
| `Conversation` | Multi-turn dialog session (user/assistant history + current agent) |
| `Citation` | Reference to a knowledge-base passage (source, section, score) |
| `ConversationResponse` | Bot response (text + citations) |
| `ConversationEvent` | Tracking event (question, answer, latency, escalation) |
| `KnowledgeChunk` | Knowledge unit indexed in the vector store |
| `GuardrailResult` | Guardrail evaluation result (PASS, OFF_TOPIC, LOW_CONFIDENCE) |
| `AgentProfile` | Specialized agent profile (id, name, system prompt, KB domain, intent keywords) |
| `AgentRegistry` | Registry of available agents with lookup by id and default fallback |
| `SourceDocument` | **Pivot** format for a KB source document (sourceType, sourceId, title, url, content, domain, language, updatedAt, contentHash) — normalizes any heterogeneous source before ingestion |
| `ContentHash` | SHA-256 utility for normalized content (sync idempotency key) |
| `SyncReport` | Result of a KB sync (processed, ingested, skipped, deleted) |

### Services

| Service | Responsibility |
|---------|---------------|
| `ConversationOrchestrator` | Unified RAG pipeline (sync + streaming) with multi-agent routing: intent classification → domain-filtered vector search → generation with dynamic system prompt |
| `ConversationService` | Legacy synchronous RAG pipeline (still functional but replaced by the orchestrator) |
| `StreamingConversationService` | Legacy streaming RAG pipeline (replaced by the orchestrator) |
| `IntentClassifier` | Classifies the user's question to route it to the appropriate agent (keyword scoring with session stickiness) |
| `KnowledgeIngestionService` | One-off ingestion (upload `POST /ingest`): delegates chunking to `TextChunker` and indexes with a domain tag |
| `KnowledgeSyncService` | Idempotent **multi-source** sync: iterates through connectors, compares `contentHash` with the ledger (skip if unchanged), re-ingests modified documents (delete + re-chunk), removes disappeared documents (deletion diff) |
| `TextChunker` | Shared semantic chunking (paragraphs, size/overlap, section extraction) — reused by one-off ingestion and sync |
| `EscalationDetector` | Detects requests requiring human transfer |
| `GuardrailService` | Pre/post-search filter: off-topic (patterns) + low-confidence (score threshold) |
| `QueryReformulator` | Reformulates follow-up questions by including conversation context |

### IN Ports (Use Cases)

| Port | Implemented by |
|------|----------------|
| `AskQuestionUseCase` | `ConversationOrchestrator` |
| `IngestKnowledgeUseCase` | `KnowledgeIngestionService` |
| `SyncKnowledgeSourceUseCase` | `KnowledgeSyncService` |

### OUT Ports (Inverted Dependencies)

| Port | Contract | Adapters |
|------|---------|----------|
| `LlmPort` | Generate a complete response (blocking `.call()`) + variant with dynamic system prompt | `MistralLlmAdapter`, `OllamaLlmAdapter` |
| `LlmStreamingPort` | Stream response tokens (`TokenStream`) + variant with dynamic system prompt | `MistralLlmAdapter`, `OllamaLlmAdapter` |
| `VectorSearchPort` | Search relevant chunks (global or domain-filtered) | `PgVectorStoreAdapter` |
| `VectorStorePort` | Store a chunk (`store` legacy + `storeChunk` with metadata enriched from a `SourceDocument`) and delete by source (`deleteBySource`) | `PgVectorStoreAdapter` |
| `KnowledgeSourceConnector` | List `SourceDocument` entries from a source (`sourceType()` + `fetchAll()`) — one connector per source type | `MarkdownFolderConnector` (reference); Confluence/PDF/DB coming later |
| `KnowledgeSourceStatePort` | Sync ledger: known hash, upsert, id list, deletion | `JpaKnowledgeSourceStateAdapter` (`kb_source_state` table) |
| `ConversationEventStore` | Persist conversation events | `JpaConversationEventStore` in Docker runtime; `InMemoryConversationEventStore` for local/dev/tests |
| `ConversationStore` | Load/save session state (`load`/`save`) | `RedisConversationStore` in Docker runtime; `InMemoryConversationStore` for local/dev/tests |

> **Note**: Each LLM adapter implements **both ports** (`LlmPort` + `LlmStreamingPort`). A single Spring bean satisfies both interfaces.
> The `SpeechToTextPort` and `TextToSpeechPort` ports are no longer used on the Java side — STT/TTS are handled by the Python agent via Gradium.

## Processing Pipeline

### Multi-Agent Routing

```
User question
    │
    ▼
IntentClassifier.classify(question, currentAgentId)
    │
    ├─ Keyword score ≥ 1 → route to the agent with the best score
    │
    ├─ Score = 0 + current agent in session → stay on current agent (stickiness)
    │
    └─ Score = 0 + no current agent → fallback to default agent (support)
```

**Available agents:**

| Agent | KB domain | Trigger keywords (excerpt) |
|-------|-----------|------|
| **Technical support** | `support` | connection, wifi, router, speed, outage, indicator light, reset... |
| **Billing** | `billing` | invoice, payment, direct debit, price, subscription, cancellation... |
| **Sales** | `commercial` | subscribe, fiber, moving, number portability, option, TV, referral... |

### Text Mode (REST — Synchronous)

```
Client → POST /api/conversation/ask
         → ConversationOrchestrator.ask()
           → EscalationDetector.shouldEscalate()  [short-circuit if yes]
           → GuardrailService.checkBeforeSearch()  [greeting → direct response]
                                                   [off-topic → short-circuit]
           → IntentClassifier.classify()           [routing to agent]
           → QueryReformulator.reformulate()       [conversation context]
           → VectorSearchPort.searchRelevant(domain) [domain-filtered retrieval]
           → GuardrailService.checkAfterSearch()   [low-confidence → short-circuit]
           → LlmPort.generateAnswer(systemPrompt)  [generation with agent prompt]
           → ConversationEventStore.save()         [tracking]
         ← JSON { answer, citations, conversationId }
```

### Target V1 Voice Mode (Pipecat WebRTC — Optimized Pipeline)

```mermaid
sequenceDiagram
    participant FE as Pipecat WebRTC UI
    participant BOT as Pipecat Bot
    participant VAD as Silero VAD (server)
    participant STT as Gradium STT
    participant BE as Backend Java
    participant LLM as Mistral API
    participant TTS as Gradium TTS

    Note over FE,BOT: User joins the WebRTC session
    FE->>BOT: WebRTC audio stream

    BOT->>VAD: Server endpointing and barge-in
    BOT->>STT: GradiumSTTService (streaming)
    STT-->>BOT: Transcript

    BOT->>BE: GET /api/conversation/ask-stream?question=...
    Note over BE: Vector search (~200ms)
    BE->>LLM: ChatClient.stream()
    LLM-->>BE: token stream

    loop For each detected sentence
        BE-->>BOT: SSE event:chunk {"text":"token..."}
        Note over BOT: StreamingRAGProcessor pushes one TextFrame per sentence
        BOT->>TTS: GradiumTTSService
        TTS-->>BOT: Audio chunks
        BOT-->>FE: Audio WebRTC
    end

    BE-->>BOT: SSE event:done

    Note over FE,BOT: --- Barge-in (interruption) ---
    FE->>BOT: User speaks during the response
    BOT->>BOT: Pipecat interrupts audio output and the current pipeline
    Note over FE: New cycle: audio -> STT -> RAG
```

**Perceived latency gain:** the optimized streaming path targets a first audible
sentence around **700ms** instead of ~2.2s in sequential mode. Per
[`ADR-0018`](adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md), this
is an aspirational user-experience target; the measurable pilot criterion is
`time_to_first_audio` p95 below 800 ms in a pre-warmed, co-located environment
(the stub-era number, **revised by [`ADR-0029`](adrs/ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md)**
for a real backend to mouth-to-ear p95 ≤ 1.5 s / `time_to_first_audio` p95 ≤ 1.2 s).

### Legacy WebSocket Protocol (React Frontend ↔ Bridge)

This protocol remains documented for the historical POC and fallback tests. The
V1 web target is the Pipecat WebRTC transport.

| Direction | Message | Format | When |
|-----------|---------|--------|-------|
| Client → | Audio | Binary (PCM 16kHz mono) | After end-of-speech detection (VAD) |
| Client → | End | Text `"END_OF_SPEECH"` | After sending the audio buffer |
| Client → | Interruption | Text `"BARGE_IN"` | User speaks while the bot is responding |
| Client → | Language | JSON `{"type":"set_language","language":"fr\|en"}` | Language toggle |
| → Client | Transcription | JSON `{"type":"transcription","text":"..."}` | After STT |
| → Client | Text chunk | JSON `{"type":"answer_chunk","text":"..."}` | Each sentence (streaming) |
| → Client | Sentence audio | Binary (WAV 16kHz mono) | After TTS for each sentence |
| → Client | Response end | JSON `{"type":"answer_done","text":"..."}` | End of complete generation |
| → Client | Language ack | JSON `{"type":"language_changed","language":"..."}` | After set_language |

### Target V1 Telephony Mode (Twilio Media Streams → Pipecat + Gradium)

The V1 target serves telephony through `agent/bot.py` and the Twilio transport
created by Pipecat (`create_transport`). WebRTC and Twilio share the same
pipeline: transport input → server VAD → Gradium STT → RAG SSE → Gradium TTS →
transport output.

```
Inbound phone call
  → Twilio → POST /api/twilio/voice (webhook on Java backend)
  ← TwiML <Response><Connect><Stream url="wss://.../ws/twilio"/></Connect></Response>

  → Twilio Media Streams → Pipecat Twilio transport
  → Silero server VAD
  → Gradium STT streaming → transcription
  → GET /api/conversation/ask-stream (SSE) → response streamed by sentence
  → Gradium TTS streaming
  → Pipecat Twilio transport → audio streamed to the caller
```

The `telephony.py`, `audio_codec.py`, `turn_detector.py`, `stt_streaming.py`,
and `bridge_server.py` modules remain useful for the legacy/fallback path and
low-level tests, but they no longer carry the V1 target.

## Chunking Strategy

`KnowledgeIngestionService` chunks documents semantically:

1. **Paragraph-based splitting** (`\n\n`) — respects logical boundaries
2. **Target size: 500 characters** — enough for coherent context
3. **Overlap: 50 characters** — ensures continuity between chunks
4. **Section extraction** — the Markdown heading `## ...` is propagated as metadata
5. **Domain tag** — each chunk is tagged with the agent domain (`support`, `billing`, `commercial`)

Each chunk is then:
- Transformed into a vector through `nomic-embed-text` (768 dimensions)
- Stored in pgvector with an HNSW index for fast search
- Annotated with its metadata (source, section, index, **domain**)
- Filterable by domain during vector search (through `FilterExpression`)

## Two Distinct AI Models: LLM (Generation) vs Embedding (Vectorization)

The system uses **two separate AI models**, which should not be confused:

| Role | Model (default) | Provider | When |
|------|-----------------|-------------|-------|
| **LLM / chat** (writes the response) | `mistral-small-latest` | **Mistral AI** (cloud API) | On every response generation |
| **Embedding** (text → vector) | `nomic-embed-text` (768 dim) | **Ollama** (local) | During ingestion (each chunk) AND on every request (the question) |

> The LLM provider is configurable (`voice-support.llm.provider`: `mistral-api` by default, `ollama` as an alternative). Embedding is currently **always** served by Ollama: `MistralAiEmbeddingAutoConfiguration` is excluded in `VoiceSupportApplication`. Moving embeddings to Mistral (`mistral-embed`, 1024 dim) would require changing `pgvector.dimensions`, recreating the `vector_store` table, and resynchronizing.

## Multi-Source Knowledge Base (Synchronization)

> Dedicated documentation: [`knowledge-base-technical.md`](../knowledge-base/knowledge-base-technical.md)
> (detailed architecture + connector-based extension) and
> [`knowledge-base-guide.md`](../knowledge-base/knowledge-base-guide.md) (writing/publishing
> content for non-dev contributors).

Beyond one-off upload (`POST /api/knowledge/ingest`), the KB is fed by **source
connectors** synchronized into a single **pivot** format (`SourceDocument`). This
makes it possible to add heterogeneous sources (Markdown, Confluence, PDF,
database) without touching the core.

```mermaid
graph TB
    subgraph sources ["Sources (one connector per type)"]
        MD["MarkdownFolderConnector<br/>knowledge-base/*.md"]
        FUT["Confluence / PDF / DB<br/>(coming later)"]
    end

    subgraph domain ["Domain"]
        SYNC["KnowledgeSyncService"]
        CHUNK["TextChunker"]
    end

    subgraph store ["PostgreSQL (single database)"]
        LEDGER[("kb_source_state<br/>sync ledger")]
        VEC[("vector_store<br/>chunks + embeddings + metadata JSONB")]
    end

    OLLAMA["Ollama<br/>nomic-embed-text"]
    SCHED["KnowledgeSyncScheduler<br/>cron (scheduled pull)"]
    REST["POST /api/knowledge/sync"]

    SCHED --> SYNC
    REST --> SYNC
    MD -->|"SourceDocument (pivot)"| SYNC
    FUT -.->|"SourceDocument (pivot)"| SYNC
    SYNC -->|"known hash? upsert"| LEDGER
    SYNC --> CHUNK
    CHUNK -->|"chunks"| VEC
    SYNC -->|"embedding"| OLLAMA
    OLLAMA -->|"768d vectors"| VEC
```

**Sync loop (idempotent) per source:**

1. The connector returns all its `SourceDocument` entries (`fetchAll()`), each carrying a `contentHash` (SHA-256).
2. For each document: if the hash is identical to the ledger value → **skip** (no re-embed). Otherwise → `deleteBySource`, then re-chunk + re-store, and update the ledger.
3. **Deletion diff**: any `sourceId` present in the ledger but absent from the source is removed from the vector store and the ledger.

**Reference connector — `MarkdownFolderConnector`:** reads `knowledge-base/*.md`,
resolves `domain` from **YAML front matter** (`domain: billing`), `sourceId` =
filename, `updatedAt` = file modification date. It replaces manual `curl`
seeding.

**Storage:** everything lives in **a single Postgres** (image
`pgvector/pgvector`). The `vector_store` table (managed by Spring AI) stores
content + embeddings + metadata as **JSONB** (so enriching metadata requires no
`ALTER`). The `kb_source_state` table (JPA, Hibernate `ddl-auto: update`) stores
only sync accounting (hash, counters), not content.

**Scheduling:** `KnowledgeSyncScheduler` runs `syncAll()` via cron
(`voice-support.knowledge.sync-cron`, hourly by default). Setting
`KB_SYNC_CRON=-` disables scheduled sync.

## Escalation Detection

Per [ADR-0019](adrs/ADR-0019-escalation-rules-and-handoff-contract.md), the Java
backend owns escalation decisions. Channel adapters, Pipecat, WhatsApp, and
future contact-center integrations must display or speak the backend decision
instead of replacing support policy locally.

`EscalationDetector` is a pure domain component that short-circuits the RAG pipeline:

```
User question
    │
    ▼
EscalationDetector.shouldEscalate()
    │
    ├─ YES → predefined message + event escalated=true + STOP
    │
    └─ NO → normal RAG pipeline
```

Generic support triggers include cancellation, complaint, refund, dispute,
technician or field intervention request, GDPR/privacy, suspected hacking,
explicit advisor request, repeated automation failure, and strong frustration.

Billing/BSS triggers include unavailable account data, inconsistent invoice
evidence, unusable invoice extraction, low-confidence monetary lines, or a
deterministic comparison that cannot explain the requested invoice delta.

Future contact-center handoff uses an `EscalationHandoff` envelope with
`conversation_id`, `channel`, `external_session_id`, `message_id`,
`customer_reference`, `current_agent_id`, `reason_code`, `priority`, `summary`,
`last_user_message`, evidence references, and recommended next action.

Escalation is **instantaneous** (<1ms) because it goes through neither the vector
store nor the LLM.

## Conversation Memory Management

Session state is accessed through the `ConversationStore` port (`load(id)` /
`save(id, conversation)`), which makes `ConversationOrchestrator` **stateless at
the JVM level**: it no longer keeps an internal map. The history of the last 6
turns is injected into the LLM prompt to preserve multi-turn coherence.

In local/dev/test, in-memory adapters remain available by default so the system
can start without infrastructure. In Docker runtime, `CONVERSATION_STORE=redis`
and `CONVERSATION_EVENT_STORE=jpa` respectively activate
`RedisConversationStore` for active sessions and `JpaConversationEventStore` for
durable events. The explicit `load` → mutation → `save` pattern remains
compatible with a distributed store without depending on in-memory reference
identity.

## Latency Budget

### Streaming Mode (Optimized Pipeline — Target Budget)

| Step | Time | Component | Perceived impact |
|-------|-------|-----------|-------------|
| Gradium STT (REST batch) | ~200ms | Voice Agent | Blocking |
| Vector search (pgvector HNSW) | ~200ms | Java Backend | Blocking |
| LLM first token (Mistral API) | ~150ms | Java Backend → Mistral | Blocking |
| Sentence detection | ~100ms | Voice Agent (splitter) | Token accumulation |
| TTS first sentence | ~200ms | Voice Agent → Gradium | |
| **First audible sentence** | **~700ms** | | |
| Complete LLM response (total) | ~1200ms | Java Backend → Mistral | In parallel with TTS |
| TTS all sentences | ~400ms | Voice Agent → Gradium | Sequential per sentence |

This table is a target budget, not a production SLO.
[ADR-0018](adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md) defines
the stub-era pilot criterion (`time_to_first_audio` p95 below 800 ms), **revised
for a real backend by [ADR-0029](adrs/ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md)**
(mouth-to-ear p95 ≤ 1.5 s / `time_to_first_audio` p95 ≤ 1.2 s),
and keeps production SLO acceptance gated by
[ADR-0010](adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md):
per-step/channel observability, dashboards, alerting, degraded modes,
retries/timeouts, and provider outage tests.

### Synchronous Mode (Fallback / Text Mode)

| Step | Time | Component |
|-------|-------|-----------|
| Gradium STT | ~200ms | Voice Agent |
| Vector search | ~200ms | Java Backend |
| Complete LLM response (Mistral API) | ~1200ms | Java Backend |
| Gradium TTS (full text) | ~300ms | Voice Agent |
| **Total** | **~1.9s** | |

## Configuration LLM

The LLM provider is configurable through `voice-support.llm.provider`:

| Provider | Value | Streaming | First-token latency | Usage |
|----------|--------|-----------|--------------------|----|
| **Mistral API** (default) | `mistral-api` | Yes (SSE) | ~150ms | Production |
| Ollama local | `ollama` | Yes (SSE) | ~500ms | Offline development |

Both adapters implement `LlmPort` (blocking) and `LlmStreamingPort`. The domain
exposes a `TokenStream`; adapters may use Reactor or the provider's streaming
API internally, but that dependency does not cross the port.

## Extensibility

### Replacing the LLM

To add a new LLM provider (for example OpenAI):

1. Create `OpenAILlmAdapter implements LlmPort, LlmStreamingPort` in `adapter/out/llm/`
2. Add a conditional `@Bean` in `DomainServiceConfig` (for example `@ConditionalOnProperty`)
3. Add configuration in `application.yml`
4. No domain change required

### Replacing Gradium (STT/TTS)

On this branch, STT lives in `voice-agent/stt_validation/gradium_provider.py`
(batch + streaming) behind the `SttProvider` protocol, and TTS lives in
`voice-agent/tts_synthesis/gradium_tts_provider.py` (batch + streaming) behind the
TTS port; swap providers by adding a new implementation and selecting it in the
respective `provider_factory.py`. (The legacy `main` Pipecat agent used
`agent/gradium_stt.py` / `gradium_tts.py`.)

### Adding a Transport

New target transports should be added through the Pipecat voice agent first.
`agent/bot.py` creates the runtime transport and keeps the shared pipeline:
transport input → server VAD → Gradium STT → backend SSE → Gradium TTS →
transport output.

To add a V1 transport such as native SIP, LiveKit, or another WebRTC gateway,
extend the Pipecat transport creation path and keep the Java backend contract
unchanged. The custom bridge (`bridge_server.py`, `ws_server.py`,
`twilio_server.py`) remains available for fallback and comparison, but should not
be the default extension path for new production channels.

## Architecture Decisions

The canonical architecture decisions are the formal ADRs in [`adrs/`](adrs/).
This page no longer maintains inline ADRs to avoid numbering conflicts and
contradictory decisions.

The former inline ADRs from this page were migrated as follows:

| Former inline ADR | Status in the formal registry |
|---|---|
| ADR-001 Modular pipeline rather than Realtime API | Covered by [ADR-0012](adrs/ADR-0012-modular-voice-pipeline-over-realtime-api.md) |
| ADR-002 Gradium for STT/TTS via Pipecat | Covered by [ADR-0002](adrs/ADR-0002-pipecat-gradium-target-voice-path.md) |
| ADR-003 Hybrid Java + Python architecture | Covered by [ADR-0001](adrs/ADR-0001-java-backend-owns-conversation-domain.md), [ADR-0002](adrs/ADR-0002-pipecat-gradium-target-voice-path.md), and [ADR-0012](adrs/ADR-0012-modular-voice-pipeline-over-realtime-api.md) |
| ADR-004 In-memory event store rather than JPA | Superseded by [ADR-0008](adrs/ADR-0008-redis-active-sessions-postgres-durable-events.md) |
| ADR-005 Inter-step streaming | Covered by [ADR-0013](adrs/ADR-0013-tokenstream-and-backend-sse-streaming-contract.md) |
| ADR-006 Legacy browser VAD | Covered as a legacy path by [ADR-0016](adrs/ADR-0016-legacy-bridge-is-fallback-and-comparison-path.md) |
| ADR-007 Guardrails | Covered by [ADR-0014](adrs/ADR-0014-domain-guardrails-before-and-after-rag.md) |
| ADR-008 Multi-agent routing | Covered by [ADR-0015](adrs/ADR-0015-keyword-routing-with-session-stickiness.md) |
| ADR-009 Custom bridge latency optimization | Covered as a legacy path by [ADR-0016](adrs/ADR-0016-legacy-bridge-is-fallback-and-comparison-path.md) |
| ADR-010 Pipecat V1 target | Covered by [ADR-0002](adrs/ADR-0002-pipecat-gradium-target-voice-path.md) |
| ADR-011 Multi-source KB ingestion | Covered by [ADR-0007](adrs/ADR-0007-source-document-knowledge-sync.md) |
| Voice latency targets and measurement | Covered by [ADR-0018](adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md) |
