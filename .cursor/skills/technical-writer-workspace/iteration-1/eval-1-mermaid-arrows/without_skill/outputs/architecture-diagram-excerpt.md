```mermaid
graph TB
    %% ─── Clients ───
    Browser["👤 Browser"]
    Twilio["👤 Twilio"]

    %% ─── Notre code : Frontend / UI ───
    subgraph frontend ["🟢 Web UI"]
        PipecatUI[Pipecat prebuilt UI WebRTC :7860]
        VoiceChat[React VoiceChat legacy :5173]
    end

    %% ─── Notre code : Voice Agent ───
    subgraph voiceAgent ["🟢 Voice Agent — Python"]
        PipecatBot[agent/bot.py Pipecat pipeline]
        StreamingRAG[streaming_rag_processor.py]
        BridgeServer[bridge_server.py legacy fallback]
        BackendClient[backend_client.py]
    end

    %% ─── Externe : Gradium (proche du voice agent qui l'appelle) ───
    subgraph gradium ["🔴 Gradium Cloud API"]
        GradiumSTT[STT — api.gradium.ai]
        GradiumTTS[TTS — wss://api.gradium.ai]
    end

    %% ─── Notre code : Java Backend ───
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
            RAGPipeline["Pipeline RAG"]
        end
        subgraph adaptersOut [Adapters OUT]
            PgVecAdapter[PgVectorStoreAdapter]
            MistralAdapter[MistralLlmAdapter]
            OllamaAdapter[OllamaLlmAdapter]
        end
    end

    %% ─── Externes : LLM + DB (proches du backend qui les appelle) ───
    PgVector["🔴 PostgreSQL + pgvector :5433"]
    MistralAPI["🔴 Mistral AI Cloud"]
    Ollama["🔴 Ollama Local :11434"]

    %% ─── Flux entrants ───
    Browser -->|"WebRTC :7860"| PipecatUI
    PipecatUI --> PipecatBot
    Twilio -->|"Media Streams"| PipecatBot
    Browser -.->|"legacy ws:8765"| VoiceChat
    VoiceChat -.->|"legacy PCM + JSON"| BridgeServer

    %% ─── Voice Agent → Gradium (externe) ───
    PipecatBot -->|"GradiumSTTService streaming"| GradiumSTT
    BridgeServer -.->|"legacy HTTPS POST"| GradiumSTT

    %% ─── Voice Agent → Backend (interne) ───
    PipecatBot --> StreamingRAG
    StreamingRAG --> BackendClient
    BackendClient -->|"target V1 GET SSE /ask-stream"| StreamController
    BridgeServer -.->|"legacy fallback POST /ask"| ConvController

    %% ─── Backend interne ───
    StreamController --> Orchestrator
    ConvController --> Orchestrator
    Orchestrator --> IntentClass
    IntentClass --> AgentReg
    Orchestrator --> EscDetector
    Orchestrator --> RAGPipeline

    %% ─── Pipeline RAG → Retrieval + Generation adapters ───
    RAGPipeline -->|"retrieval query"| PgVecAdapter
    PgVecAdapter -->|"SQL + HNSW retrieval"| PgVector
    RAGPipeline -->|"generation prompt"| MistralAdapter
    MistralAdapter -->|"HTTPS streaming generation"| MistralAPI
    RAGPipeline -.->|"generation fallback"| OllamaAdapter
    OllamaAdapter -.->|"HTTP streaming generation"| Ollama

    %% ─── Voice Agent → TTS (externe) ───
    PipecatBot -->|"GradiumTTSService streaming"| GradiumTTS
    BridgeServer -.->|"legacy WSS"| GradiumTTS
```
