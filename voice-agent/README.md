# Voice Agent — Pipecat + Gradium

Agent vocal temps réel pour le support télécom, utilisant :
- **[Pipecat](https://pipecat.ai)** comme framework d'orchestration audio/IA
- **[Gradium](https://gradium.ai)** pour le STT (Speech-to-Text) et TTS (Text-to-Speech)
- Le **backend Java** (Spring Boot) pour le RAG (retrieval + LLM)

## Architecture

La cible V1 est le bot Pipecat (`agent/bot.py`) avec Gradium pour STT/TTS :
WebRTC côté web et Twilio Media Streams côté téléphonie. Le bridge WebSocket
custom (`agent/bridge_server.py`) reste disponible comme chemin POC historique /
fallback, mais ce n'est plus le lancement recommandé pour la V1.

```
Browser/Téléphone
     │
     ▼ WebRTC ou Twilio Media Streams
┌─────────────────────────────┐
│      Pipecat Pipeline       │
│  ┌───────┐  ┌───┐  ┌───┐   │
│  │Gradium│→ │RAG│→ │Gradium││
│  │ STT   │  │API│  │ TTS  ││
│  └───────┘  └───┘  └───────┘│
└─────────────────────────────┘
                │
                ▼ HTTP SSE /api/conversation/ask-stream
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

### Lancement recommandé — Pipecat

**Mode WebRTC (web) :**
```bash
python -m agent.bot -t webrtc
# → UI prebuilt sur http://localhost:7860
```

**Mode multi-transport (web + téléphonie) :**
```bash
python -m agent.bot
```

**Mode Twilio seul :**
```bash
python -m agent.bot -t twilio -x <host-public>
```

### Chemin legacy / fallback

Le projet contient encore deux implémentations qui peuvent tourner en parallèle
(backend Java partagé), mais leur statut n'est pas équivalent :

| | Legacy / fallback | Cible V1 |
|---|---|---|
| Entrée | `python -u -m agent.bridge_server` | `python -m agent.bot` |
| Web | `ws://localhost:8765` + frontend React (`:5173`) | WebRTC + UI prebuilt sur `http://localhost:7860` |
| Téléphonie | `ws://localhost:8766` (Twilio Media Streams) | `python -m agent.bot -t twilio -x <host-public>` |
| STT | Gradium REST (batch) | Gradium streaming |
| VAD | navigateur + heuristique RMS | Silero (serveur) |

## Configuration

| Variable | Défaut | Description |
|----------|--------|-------------|
| `GRADIUM_API_KEY` | — | Clé API Gradium (obligatoire) |
| `GRADIUM_VOICE_ID` | `b35yykvVppLXyw_l` | ID de la voix Gradium ([catalogue](https://docs.gradium.ai/guides/voices/all-voices)) |
| `BACKEND_URL` | `http://localhost:8081` | URL du backend Java |
| `VOICE_AGENT_HOST` | `0.0.0.0` | Host d'écoute du bridge legacy |
| `VOICE_AGENT_PORT` | `8765` | Port WebSocket du bridge legacy navigateur |
| `TWILIO_WS_PORT` | `8766` | Port WebSocket du bridge legacy Twilio |

## Pipeline vocal

1. **Audio in** → Le navigateur envoie l'audio via WebRTC, Twilio via Media Streams
2. **Pipecat + Gradium STT** → Transcription temps réel avec VAD serveur
3. **RAG Processor** → Appel SSE au backend Java (`GET /api/conversation/ask-stream?question=...&conversation_id=...`)
4. **Gradium TTS** → Synthèse vocale du texte de réponse dans le pipeline Pipecat
5. **Audio out** → Renvoi du flux audio au client

## Formats audio supportés

| Transport | Format | Sample rate |
|-----------|--------|-------------|
| Navigateur (Pipecat WebRTC) | PCM dans le pipeline | géré par Pipecat |
| Twilio (Media Streams) | μ-law | 8 kHz |
| Navigateur legacy (WebSocket) | PCM 16-bit | 16 kHz |

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
