# Voice Runtime HTTP API Contract (Sprint 5)

**Scope:** the HTTP surface exposed by the Python voice runtime
(`voice-agent/web_voice/server.py`) for the Voice2Voice web loop (US-019).
**Status:** current on `feat/sprint-5-backend-bridge`. Single source of truth for
these endpoints — no code-only contract remains for the sprint.
**Related:** [conversation contract ADR-0021](adrs/ADR-0021-conversation-backend-answer-contract.md),
[voice journey timing](../observability/voice-journey-timing.md).

## Server

```bash
cd voice-agent
python3 -m web_voice.server \
  --host 127.0.0.1 --port 8090 \
  --provider {fixture|gradium} \
  --runtime {pipecat|stdlib} \
  --backend {stub|http}
```

| Flag | Env | Default | Meaning |
|---|---|---|---|
| `--provider` | — | `gradium` | STT/TTS provider: `fixture` (offline) or `gradium` (live) |
| `--runtime` | `VOICE_RUNTIME` | `pipecat` | Voice runtime: `pipecat` (ADR-0002 target) or `stdlib` (fallback/comparison, ADR-0016) |
| `--backend` | `VOICE_BACKEND` | `stub` | Conversation backend: `stub` (deterministic offline) or `http` (real endpoint, see below) |

`http` backend configuration (TASK-WEB-003-C):

| Env | Required | Meaning |
|---|---|---|
| `VOICE_BACKEND_URL` | yes (for `http`) | Conversation endpoint URL |
| `VOICE_BACKEND_API_KEY` | no | Sent as `x-api-key`; never logged or echoed |
| `VOICE_BACKEND_TIMEOUT_S` | no (default `8.0`) | Per-request timeout |

All endpoints are same-origin, unauthenticated on the pilot host (identity is
gated by OQ-001 / RF-006). Requests carry an optional envelope via query params
`conversation_id`, `session_id`, `correlation_id`; missing ids are generated.

## Common conventions

- **Audio in** is raw **PCM16 mono 16 kHz** (`Content-Type: audio/pcm`).
- **Audio out** is **WAV** (`audio/wav`, PCM16 mono + 44-byte header).
- **Errors** are JSON with a stable `error_code` and a **sanitized** `error_reason`
  (RF-013): no raw audio, filesystem path, provider text or secret. Every response
  carries a `correlation_id` for tracing.
- Size guards: audio `> 25 MiB` → `413 {"error":"audio_too_large"}`; TTS text
  `> 5000` chars → `413 {"error":"text_too_large"}`.

## `POST /api/voice/stt` — transcribe

Voice-in only (no answer, no audio out).

- **Request:** body = PCM16 audio bytes; query = optional envelope ids.
- **200** (`SttOutcome.success`) / **502** (`failed` or `unavailable`), JSON:

```json
{
  "transcript": "bonjour pourquoi ma facture augmente",
  "provider": "gradium-stt",
  "outcome": "success",
  "duration_ms": 2301.4,
  "stt_request_ms": 2296.0,
  "correlation_id": "…",
  "error_code": null,
  "error_reason": null
}
```

On failure `outcome` is `failed`/`unavailable`, `transcript` is `""`, and
`error_code`/`error_reason` are populated (sanitized). No transcript is invented.

## `POST /api/voice/tts?text=…` — synthesize

Voice-out only.

- **Request:** `text` query param (URL-encoded); query = optional envelope ids.
- **200:** `audio/wav` body (the spoken text).
- **502:** JSON `SynthesisResult` on failure/unavailable:

```json
{
  "provider": "gradium-tts",
  "outcome": "failed",
  "duration_ms": 12.0,
  "tts_request_ms": 11.5,
  "correlation_id": "…",
  "audio_format": "pcm_16000",
  "audio_bytes": 0,
  "error_code": "tts_error",
  "error_reason": "…"
}
```

Empty text is reported `unavailable` (not a failure) and invents no audio.

## `POST /api/voice/turn` — full Voice2Voice loop

Runs `STT → backend answer → TTS` in one call (the answering loop, TASK-WEB-003-D).

- **Request:** body = PCM16 audio bytes; query = optional envelope ids.
- **200:** `audio/wav` body = the **spoken answer**, plus response headers:

| Header | Meaning |
|---|---|
| `X-Correlation-Id` | Correlation id for the turn |
| `X-Voice-Transcript` | The transcript (percent-encoded UTF-8) |
| `X-Voice-Answer` | The spoken answer text (percent-encoded UTF-8) |
| `X-Answer-Provider` | Backend that answered (`stub-backend` / `http-backend`) |
| `X-Answer-Outcome` | `success` or `degraded` |
| `X-Answer-Degraded-Reason` | Present only when degraded: `backend_unavailable` / `low_confidence` / `empty_answer` |

Headers are sent only to the requesting client and never written to server logs.

- **502 (JSON), fails closed** when the loop cannot produce audio:
  - STT did not succeed → the `TranscriptResult` JSON (`outcome: failed`), or
    `{"error":"no_transcript"}`.
  - TTS produced no audio → the `SynthesisResult` JSON, or `{"error":"no_audio"}`.

### Degraded mode (TASK-WEB-003-F)

When the backend is unavailable, not confident, or returns an empty answer, the
turn does **not** fail: it speaks a **safe fallback** (no invented billing
content, DEC-002) and returns **200** with `X-Answer-Outcome: degraded` and a
sanitized `X-Answer-Degraded-Reason`. Only an empty transcript (nothing to answer)
stays silent by design. See ADR-0021.

## Telemetry

Every call emits OpenTelemetry-style spans on a per-request `TelemetryRecorder`
sharing one correlation id: `web.voice.ingress`, `voice.end_of_turn`,
`stt.request`, `backend.first_token` + `backend.request`, `voice.tts.first_audio`,
`web.voice.egress`. These feed the six US-036 slices
(see [voice-journey-timing](../observability/voice-journey-timing.md)). Degraded
turns carry `outcome=degraded`, `degraded=true` and the sanitized
`degraded_reason`/`error_code` (lengths only for any text).
