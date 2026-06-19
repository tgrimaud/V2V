# Voice Support Bot

Agent support client vocal pour le domaine Telecom/FAI, alimenté par RAG sur une base de connaissance, accessible via navigateur web et téléphonie classique (Twilio).

## Stack

| Couche | Technologie |
|--------|------------|
| Backend | Java 21, Spring Boot 3.4, Spring AI 1.0 |
| LLM | Ollama (llama3.1) — configurable vers OpenAI |
| Embeddings | nomic-embed-text via Ollama |
| Vector Store | PostgreSQL + pgvector |
| STT | Deepgram API (streaming) |
| TTS | Piper (local, voix FR) |
| Téléphonie | Twilio Media Streams |
| Frontend | React 19, TypeScript, Vite, TailwindCSS 4 |

## Architecture

Architecture hexagonale (ports & adapters) :

```
domain/
├── model/          → Conversation, KnowledgeChunk, Citation
├── port/in/        → AskQuestionUseCase, IngestKnowledgeUseCase
├── port/out/       → SpeechToTextPort, TextToSpeechPort, VectorSearchPort, LlmPort
└── service/        → ConversationService, KnowledgeIngestionService

infrastructure/
├── adapter/in/     → REST controllers, WebSocket handlers, Twilio webhooks
├── adapter/out/    → Ollama, pgvector, Deepgram, Piper adapters
└── config/         → Spring configuration, bean wiring
```

## Démarrage rapide

### Prérequis

- Java 21+
- Node.js 20+
- Docker & Docker Compose
- Ollama installé localement (ou via Docker)
- Compte Deepgram (API key pour le STT)

### 1. Infrastructure

```bash
docker compose up -d
```

Cela démarre PostgreSQL + pgvector, Ollama et Piper TTS.

### 2. Modèles Ollama

```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

### 3. Variables d'environnement

```bash
cp .env.example .env
# Éditer .env avec votre clé Deepgram
```

### 4. Backend

```bash
cd backend
./mvnw spring-boot:run
```

### 5. Frontend

```bash
cd frontend
npm install
npm run dev
```

L'application est accessible sur http://localhost:5173.

### 6. Ingérer la base de connaissance

```bash
curl -X POST http://localhost:8080/api/knowledge/ingest \
  -F "file=@knowledge-base/telecom-faq.md" \
  -F "source=telecom-faq"
```

### 7. Tester (mode texte)

```bash
curl -X POST http://localhost:8080/api/conversation/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Ma box ne se connecte plus, que faire ?"}'
```

## Pipeline vocal

```
Audio → STT (Deepgram) → Texte → RAG (pgvector) → LLM (Ollama) → Texte → TTS (Piper) → Audio
```

## Téléphonie (Twilio)

1. Configurer un numéro Twilio avec le webhook : `POST https://your-domain.com/api/twilio/voice`
2. Le flux audio est géré via WebSocket bidirectionnel sur `/ws/twilio`
3. Nécessite un tunnel (ngrok) pour le développement local

## Tests

```bash
cd backend && ./mvnw test
cd frontend && npm run lint
```
