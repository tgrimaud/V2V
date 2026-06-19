# Architecture — Voice Support Bot

## Vue d'ensemble

Voice Support Bot est un agent vocal intelligent qui répond aux questions de support client dans le domaine Telecom/FAI. Il utilise le pattern **RAG** (Retrieval-Augmented Generation) pour fournir des réponses factuelles basées sur une base de connaissance interne.

L'architecture est **hybride** :
- Un **backend Java** (hexagonal) gère la logique métier, le RAG, et l'administration
- Un **agent vocal Python** (Pipecat) orchestre le pipeline audio temps réel avec Gradium (STT/TTS)

## Diagramme d'architecture

```
                              ┌───────────────────────────────────────────────┐
                              │           VOICE AGENT (Python)                │
                              │                Pipecat 1.4                    │
 ┌──────────┐                 │  ┌──────────────────────────────────────┐    │
 │ Browser  │──ws:8765───────▶│  │     WebSocket Server Transport       │    │
 └──────────┘                 │  └───────────┬────────────────┬─────────┘    │
                              │              │                │               │
 ┌──────────┐                 │  ┌───────────▼──┐    ┌───────▼────────┐     │
 │ Twilio   │──ws:8766───────▶│  │  Gradium STT │    │  Gradium TTS   │     │
 └──────────┘                 │  └───────────┬──┘    └───────▲────────┘     │
                              │              │               │               │
                              │  ┌───────────▼───────────────┴──────────┐   │
                              │  │           RAG Processor               │   │
                              │  │   (HTTP POST /api/conversation/ask)   │   │
                              │  └───────────────────┬──────────────────┘   │
                              └─────────────────────┼───────────────────────┘
                                                    │ HTTP
                              ┌─────────────────────▼───────────────────────┐
                              │           JAVA BACKEND (Spring Boot)         │
                              │                                              │
 ┌──────────┐                 │  ┌─────────────────────────────────────┐    │
 │ curl/UI  │─http:8081──────▶│  │    ConversationController (REST)     │    │
 └──────────┘                 │  └──────────────┬──────────────────────┘    │
                              │                 │                            │
                              │     ╔═══════════╪══════════════════════╗     │
                              │     ║  PORTS IN │                      ║     │
                              │     ║   ┌───────▼──────────┐          ║     │
                              │     ║   │AskQuestionUseCase │          ║     │
                              │     ║   └───────┬──────────┘          ║     │
                              │     ║           │                      ║     │
                              │     ║  ╔════════╪══════════════╗       ║     │
                              │     ║  ║ DOMAIN │              ║       ║     │
                              │     ║  ║  ┌─────▼─────────────┐║       ║     │
                              │     ║  ║  │ConversationService ║       ║     │
                              │     ║  ║  │+ EscalationDetect  ║       ║     │
                              │     ║  ║  └──┬─────┬──────┬───┘║       ║     │
                              │     ║  ╚════╪═════╪══════╪════╝       ║     │
                              │     ║       │     │      │            ║     │
                              │     ║  PORTS OUT  │      │            ║     │
                              │     ║  ┌────▼──┐ ┌▼───┐ ┌▼──────┐    ║     │
                              │     ║  │LlmPort│ │Vec │ │EventSt│    ║     │
                              │     ║  └───┬───┘ └─┬──┘ └───┬───┘    ║     │
                              │     ╚══════╪═══════╪════════╪═════════╝     │
                              │            │       │        │                │
                              │  ┌─────────▼──┐ ┌──▼────────▼──┐           │
                              │  │OllamaLlm   │ │PgVectorStore  │           │
                              │  │Adapter      │ │Adapter        │           │
                              │  └─────┬──────┘ └──────┬────────┘           │
                              └────────┼───────────────┼────────────────────┘
                                       │               │
                              ┌────────▼──┐    ┌───────▼────┐
                              │  Ollama   │    │ PostgreSQL │
                              │  (LLM)   │    │ + pgvector │
                              └───────────┘    └────────────┘
```

## Séparation des responsabilités

| Composant | Langage | Responsabilité |
|-----------|---------|---------------|
| **Voice Agent** | Python (Pipecat) | Orchestration audio temps réel, transports WebSocket, VAD |
| **Gradium** | API cloud | STT (transcription) et TTS (synthèse vocale) |
| **Backend Java** | Java (Spring Boot) | RAG, LLM, logique métier, escalade, admin, persistence |
| **PostgreSQL + pgvector** | — | Stockage vectoriel et recherche de similarité |
| **Ollama** | — | Inférence LLM locale |

## Couche domaine (Pure Java)

Le domaine ne contient **aucune annotation Spring**, **aucune dépendance externe**. Il est testable avec de simples fakes.

### Modèles

| Classe | Rôle |
|--------|------|
| `Conversation` | Session de dialogue multi-tour (historique user/assistant) |
| `Citation` | Référence à un passage de la base de connaissance (source, section, score) |
| `ConversationResponse` | Réponse du bot (texte + citations) |
| `ConversationEvent` | Événement de tracking (question, réponse, latence, escalade) |
| `KnowledgeChunk` | Unité de connaissance indexée dans le vector store |

### Services

| Service | Responsabilité |
|---------|---------------|
| `ConversationService` | Orchestre le pipeline RAG : retrieval → génération → tracking |
| `KnowledgeIngestionService` | Découpe les documents en chunks et les indexe |
| `EscalationDetector` | Détecte les demandes nécessitant un transfert humain |

### Ports IN (cas d'usage)

| Port | Implémenté par |
|------|----------------|
| `AskQuestionUseCase` | `ConversationService` |
| `IngestKnowledgeUseCase` | `KnowledgeIngestionService` |

### Ports OUT (dépendances inversées)

| Port | Contrat | Adapter actuel |
|------|---------|----------------|
| `LlmPort` | Générer une réponse à partir d'un contexte | `OllamaLlmAdapter` |
| `VectorSearchPort` | Chercher les chunks pertinents | `PgVectorStoreAdapter` |
| `VectorStorePort` | Stocker un chunk avec ses embeddings | `PgVectorStoreAdapter` |
| `ConversationEventStore` | Persister les événements de conversation | `InMemoryConversationEventStore` |

> **Note** : Les ports `SpeechToTextPort` et `TextToSpeechPort` ne sont plus utilisés côté Java.
> Le STT et TTS sont désormais gérés par l'agent Pipecat (Python) via Gradium.

## Pipeline de traitement

### Mode texte (REST)

```
Client → ConversationController.ask()
         → ConversationService.ask()
           → EscalationDetector.shouldEscalate()  [court-circuit si oui]
           → VectorSearchPort.searchRelevant()     [retrieval]
           → LlmPort.generateAnswer()             [generation]
           → ConversationEventStore.save()         [tracking]
         ← ConversationResponse (answer + citations)
```

### Mode vocal (WebSocket — Pipecat + Gradium)

```
Client (Browser)              Voice Agent (Pipecat)         Java Backend
  │                              │                              │
  │──── audio PCM 16kHz ────────▶│                              │
  │                              │                              │
  │                              │── Gradium STT → texte        │
  │                              │                              │
  │                              │── HTTP POST ────────────────▶│
  │                              │   /api/conversation/ask      │
  │                              │                              │── RAG → LLM
  │                              │◀─── JSON response ──────────│
  │                              │                              │
  │                              │── Gradium TTS → audio        │
  │                              │                              │
  │◀──── audio PCM 16kHz ───────│                              │
  │                              │                              │
```

### Mode téléphonie (Twilio → Pipecat + Gradium)

```
Appel téléphonique entrant
  → Twilio → POST /api/twilio/voice (webhook sur backend Java)
  ← TwiML <Response><Connect><Stream url="ws://voice-agent:8766"/></Connect></Response>

  → Twilio WebSocket → ws://localhost:8766 (agent Pipecat)
  → Pipecat reçoit μ-law 8kHz audio frames
  → Gradium STT (input_format: ulaw_8000) → transcription
  → HTTP POST /api/conversation/ask → réponse
  → Gradium TTS (output_format: ulaw_8000) → audio
  → Audio frames retournés à Twilio → diffusé à l'appelant
```

## Stratégie de chunking

Le `KnowledgeIngestionService` découpe les documents de manière sémantique :

1. **Découpage par paragraphes** (`\n\n`) — respecte les frontières logiques
2. **Taille cible : 500 caractères** — assez pour un contexte cohérent
3. **Chevauchement : 50 caractères** — assure la continuité entre chunks
4. **Extraction de section** — le heading Markdown `## ...` est propagé comme métadonnée

Chaque chunk est ensuite :
- Transformé en vecteur via `nomic-embed-text` (768 dimensions)
- Stocké dans pgvector avec index HNSW pour recherche rapide
- Annoté avec ses métadonnées (source, section, index)

## Détection d'escalade

L'`EscalationDetector` est un composant domaine pur qui court-circuite le pipeline RAG :

```
Question utilisateur
    │
    ▼
EscalationDetector.shouldEscalate()
    │
    ├─ OUI → message pré-défini + event escalated=true + STOP
    │
    └─ NON → pipeline RAG normal
```

Mots-clés déclencheurs : résiliation, réclamation, remboursement, technicien, RGPD, piratage, frustration explicite.

L'escalade est **instantanée** (<1ms) car elle ne passe ni par le vector store ni par le LLM.

## Gestion de la mémoire conversationnelle

Chaque `conversationId` a sa propre instance de `Conversation` en mémoire (map ConcurrentHashMap). L'historique des 6 derniers tours est injecté dans le prompt LLM pour assurer la cohérence multi-tour.

Limitation actuelle : la mémoire est volatile (in-memory). La persistence JPA est prévue en roadmap.

## Budget latence

| Étape | Temps typique | Composant |
|-------|---------------|-----------|
| Gradium STT (streaming WebSocket) | ~200ms | Voice Agent (Pipecat) |
| RAG retrieval (pgvector HNSW) | ~200ms | Java Backend |
| LLM generation (Ollama local) | ~1500ms | Java Backend |
| Gradium TTS (streaming WebSocket) | ~300ms | Voice Agent (Pipecat) |
| **Total** | **~2.2s** | Cible : <2s avec streaming inter-étapes |

### Avantages de Gradium vs Deepgram/Piper

| Critère | Deepgram + Piper (ancien) | Gradium (actuel) |
|---------|--------------------------|------------------|
| Latence STT | ~300ms | ~200ms (semantic VAD) |
| Latence TTS | ~500ms (local) | ~300ms (cloud, first-byte) |
| Format téléphonie | Conversion nécessaire | Support natif `ulaw_8000` |
| Multiplexage | Non | Oui (plusieurs sessions sur 1 WS) |
| Qualité voix FR | Moyenne (Piper) | Haute (Gradium) |

## Extensibilité

### Remplacer le LLM

Pour ajouter un nouveau provider LLM (ex: OpenAI) :

1. Créer `OpenAILlmAdapter implements LlmPort` dans `adapter/out/llm/`
2. Ajouter un `@Bean` conditionnel dans `DomainServiceConfig` (ex: `@ConditionalOnProperty`)
3. Ajouter la configuration dans `application.yml`
4. Aucune modification du domaine requise

### Remplacer Gradium (STT/TTS)

Pipecat supporte de nombreux fournisseurs via ses extras :

```python
# pyproject.toml — changer l'extra
dependencies = [
    "pipecat-ai[deepgram,cartesia,websocket,silero]",  # Deepgram STT + Cartesia TTS
]
```

Modifier `ws_server.py` pour instancier le service correspondant (ex: `DeepgramSTTService`, `CartesiaTTSService`).

### Ajouter un transport

Pipecat supporte Daily (WebRTC), Twilio, LiveKit, etc. Chaque transport est un composant pipeable :

```python
from pipecat.transports.services.daily import DailyTransport
# ou
from pipecat.transports.network.websocket_server import WebSocketServerTransport
```

## Décisions d'architecture (ADR)

### ADR-001 : Pipeline modulaire plutôt que Realtime API

**Contexte** : OpenAI Realtime API et Gemini Live offrent du voice-to-voice en une seule API.

**Décision** : Pipeline STT → RAG → LLM → TTS.

**Raisons** :
- Contrôle total sur le RAG (coeur du produit)
- Pas de vendor-lock
- Local-first possible
- Coût 12x inférieur (~$0.005/min vs ~$0.06/min)

### ADR-002 : Gradium pour STT/TTS via Pipecat

**Contexte** : Le MVP initial utilisait Deepgram (STT cloud) et Piper (TTS local).

**Décision** : Migrer vers Gradium (STT + TTS) orchestré par Pipecat (Python).

**Raisons** :
- Gradium offre STT et TTS dans une seule API avec latence très basse (~200ms STT, ~300ms TTS)
- Support natif `ulaw_8000` (format téléphonie) — pas de conversion audio nécessaire
- Pipecat fournit le framework d'orchestration avec VAD intégrée, multiplexage, et transports pluggables
- La séparation Java (RAG) / Python (voix) suit le principe de responsabilité unique
- Pipecat a une intégration native Gradium (`pipecat-ai[gradium]`)

### ADR-003 : Architecture hybride Java + Python

**Contexte** : Pipecat est Python-only, le backend RAG est Java.

**Décision** : Garder les deux : Java backend comme "cerveau" (RAG), Pipecat comme "bouche/oreille" (voix).

**Raisons** :
- Le backend Java est déjà mature (hexagonal, tests, Spring AI intégré)
- Pipecat excelle dans l'orchestration audio temps réel (VAD, streaming, transports)
- Couplage lâche via HTTP (le RAG Processor appelle `/api/conversation/ask`)
- Chaque composant est déployable et scalable indépendamment
- Pas de réécriture nécessaire du code existant

### ADR-004 : In-memory event store plutôt que JPA

**Contexte** : Le tracking des conversations pourrait être en base.

**Décision** : `InMemoryConversationEventStore` (CopyOnWriteArrayList) pour le MVP.

**Raisons** :
- Simplicité de démarrage
- Pas de migration de schéma à gérer
- Suffisant pour le volume MVP
- Le port `ConversationEventStore` permet de basculer vers JPA sans toucher au domaine
