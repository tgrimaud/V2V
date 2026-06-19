# Voice Agent — Pipecat + Gradium

Agent vocal temps réel pour le support télécom, utilisant :
- **[Pipecat](https://pipecat.ai)** comme framework d'orchestration audio/IA
- **[Gradium](https://gradium.ai)** pour le STT (Speech-to-Text) et TTS (Text-to-Speech)
- Le **backend Java** (Spring Boot) pour le RAG (retrieval + LLM)

## Architecture

```
Browser/Téléphone
     │
     ▼ WebSocket (audio PCM 16kHz ou μ-law 8kHz)
┌─────────────────────────────┐
│      Pipecat Pipeline       │
│  ┌───────┐  ┌───┐  ┌───┐   │
│  │Gradium│→ │RAG│→ │Gradium││
│  │ STT   │  │API│  │ TTS  ││
│  └───────┘  └───┘  └───────┘│
└─────────────────────────────┘
                │
                ▼ HTTP POST /api/conversation/ask
         ┌─────────────┐
         │ Java Backend │
         │ (Spring AI + │
         │  pgvector)   │
         └─────────────┘
```

## Démarrage rapide

### Prérequis
- Python 3.11+
- Clé API Gradium (créer un compte sur https://gradium.ai)
- Backend Java démarré sur le port 8081

### Installation

```bash
cd voice-agent
cp .env.example .env
# Configurer GRADIUM_API_KEY dans .env

uv pip install -e .
```

### Lancement

**Mode WebSocket (navigateur) :**
```bash
python -u -m agent.bridge_server
# → écoute sur ws://localhost:8765
```

**Mode Twilio (téléphonie) :**
```bash
python -m agent.twilio_server
# → écoute sur ws://localhost:8766
```

## Configuration

| Variable | Défaut | Description |
|----------|--------|-------------|
| `GRADIUM_API_KEY` | — | Clé API Gradium (obligatoire) |
| `GRADIUM_VOICE_ID` | `b35yykvVppLXyw_l` | ID de la voix Gradium ([catalogue](https://docs.gradium.ai/guides/voices/all-voices)) |
| `BACKEND_URL` | `http://localhost:8081` | URL du backend Java |
| `VOICE_AGENT_HOST` | `0.0.0.0` | Host d'écoute WebSocket |
| `VOICE_AGENT_PORT` | `8765` | Port WebSocket (navigateur) |
| `TWILIO_WS_PORT` | `8766` | Port WebSocket (Twilio) |

## Pipeline vocal

1. **Audio in** → Le navigateur ou Twilio envoie un flux audio via WebSocket
2. **Gradium STT** → Transcription temps réel avec VAD sémantique
3. **RAG Processor** → Appel HTTP au backend Java (`POST /api/conversation/ask`)
4. **Gradium TTS** → Synthèse vocale du texte de réponse
5. **Audio out** → Renvoi du flux audio au client

## Formats audio supportés

| Transport | Format | Sample rate |
|-----------|--------|-------------|
| Navigateur (WebSocket) | PCM 16-bit | 16 kHz |
| Twilio (Media Streams) | μ-law | 8 kHz |

## Notes techniques

### Voix Gradium

Le `voice_id` doit être un identifiant valide du [catalogue Gradium](https://docs.gradium.ai/guides/voices/all-voices). La valeur `"default"` n'existe pas et provoque l'erreur `Embeddings not found`.

Voix françaises recommandées :
| Nom | Voice ID | Genre |
|-----|----------|-------|
| Elise | `b35yykvVppLXyw_l` | Féminin |
| Leo | `axlOaUiFyOZhy4nv` | Masculin |

### Protocole TTS WebSocket

Le bridge server respecte le protocole Gradium TTS :
1. Envoi du message `setup` (avec `voice_id` + `output_format`)
2. **Attente du message `ready`** (obligatoire avant d'envoyer le texte)
3. Envoi du texte + `end_of_stream`
4. Réception des chunks audio base64
5. Wrapping PCM → WAV (header 44 octets) avant envoi au navigateur

Le navigateur utilise `AudioContext.decodeAudioData()` qui nécessite un format auto-descriptif (WAV), pas du PCM brut.
