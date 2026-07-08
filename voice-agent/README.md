# Voice Agent - Pipecat + Gradium

Real-time voice agent for telecom support, using:

- **[Pipecat](https://pipecat.ai)** as the audio/AI orchestration framework
- **[Gradium](https://gradium.ai)** for STT (Speech-to-Text) and TTS (Text-to-Speech)
- The **Java backend** (Spring Boot) for RAG (retrieval + LLM)

## Architecture

The V1 target is the Pipecat bot (`agent/bot.py`) with Gradium for STT/TTS:
WebRTC on the web side and Twilio Media Streams for telephony. The custom
WebSocket bridge (`agent/bridge_server.py`) remains available as a historical
POC/fallback path, but it is no longer the recommended V1 launch path.

```
Browser/Phone
     │
     ▼ WebRTC or Twilio Media Streams
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

## Quick Start

### Prerequisites
- Python 3.11+
- Gradium API key (create an account at https://gradium.ai)
- Java backend running on port 8081

### Installation

```bash
cd voice-agent
cp .env.example .env
# Configure GRADIUM_API_KEY in .env

uv pip install -e .
```

### Recommended Launch - Pipecat

**WebRTC mode (web):**
```bash
python -m agent.bot -t webrtc
# Prebuilt UI on http://localhost:7860
```

**Multi-transport mode (web + telephony):**
```bash
python -m agent.bot
```

**Twilio-only mode:**
```bash
python -m agent.bot -t twilio -x <host-public>
```

### Legacy / Fallback Path

The project still contains two implementations that can run in parallel against
the shared Java backend, but their status is not equivalent:

| | Legacy / fallback | V1 target |
|---|---|---|
| Entry point | `python -u -m agent.bridge_server` | `python -m agent.bot` |
| Web | `ws://localhost:8765` + React frontend (`:5173`) | WebRTC + prebuilt UI on `http://localhost:7860` |
| Telephony | `ws://localhost:8766` (Twilio Media Streams) | `python -m agent.bot -t twilio -x <host-public>` |
| STT | Gradium REST (batch) | Gradium streaming |
| VAD | browser + RMS heuristic | Silero (server-side) |

## Configuration

| Variable | Default | Description |
|----------|--------|-------------|
| `GRADIUM_API_KEY` | - | Gradium API key (required) |
| `GRADIUM_VOICE_ID` | `b35yykvVppLXyw_l` | Gradium voice ID ([catalog](https://docs.gradium.ai/guides/voices/all-voices)) |
| `BACKEND_URL` | `http://localhost:8081` | Java backend URL |
| `VOICE_AGENT_HOST` | `0.0.0.0` | Legacy bridge bind host |
| `VOICE_AGENT_PORT` | `8765` | Legacy browser WebSocket bridge port |
| `TWILIO_WS_PORT` | `8766` | Legacy Twilio WebSocket bridge port |

## Voice Pipeline

1. **Audio in** -> the browser sends audio over WebRTC, Twilio over Media Streams
2. **Pipecat + Gradium STT** -> real-time transcription with server-side VAD
3. **RAG Processor** -> SSE call to the Java backend (`GET /api/conversation/ask-stream?question=...&conversation_id=...`)
4. **Gradium TTS** -> speech synthesis for the answer inside the Pipecat pipeline
5. **Audio out** -> audio stream returned to the client

## Supported Audio Formats

| Transport | Format | Sample rate |
|-----------|--------|-------------|
| Browser (Pipecat WebRTC) | PCM inside the pipeline | managed by Pipecat |
| Twilio (Media Streams) | μ-law | 8 kHz |
| Legacy browser (WebSocket) | PCM 16-bit | 16 kHz |

## Technical Notes

### Gradium Voices

The `voice_id` must be a valid identifier from the
[Gradium catalog](https://docs.gradium.ai/guides/voices/all-voices). The value
`"default"` does not exist and causes the `Embeddings not found` error.

Recommended French voices:

| Name | Voice ID | Gender |
|-----|----------|-------|
| Elise | `b35yykvVppLXyw_l` | Female |
| Leo | `axlOaUiFyOZhy4nv` | Male |

### TTS WebSocket Protocol

The bridge server follows the Gradium TTS protocol:

1. Send the `setup` message (with `voice_id` + `output_format`)
2. **Wait for the `ready` message** (required before sending text)
3. Send text + `end_of_stream`
4. Receive base64 audio chunks
5. Wrap PCM -> WAV (44-byte header) before sending it to the browser

The browser uses `AudioContext.decodeAudioData()`, which requires a
self-describing format (WAV), not raw PCM.
