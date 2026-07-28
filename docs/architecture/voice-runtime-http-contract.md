# Voice Runtime HTTP API Contract (Sprint 5–6)

**Scope:** the HTTP surface exposed by the Python voice runtime
(`voice-agent/web_voice/server.py`): the batch Voice2Voice loop (US-019, Sprint 5)
and the streaming WebRTC signaling surface (Sprint 6, TASK-WEB-007/009).
**Status:** current through `feat/sprint-6-streaming`. Single source of truth for
these endpoints — no code-only contract remains for the streaming surface. A
machine-readable OpenAPI 3 mirror is committed at
[`voice-agent/web_voice/openapi.yaml`](../../voice-agent/web_voice/openapi.yaml)
(served at `GET /api/voice/openapi.yaml`); this document stays authoritative and the
spec is kept in sync with it — a `tests/test_voice_openapi.py` drift guard fails if a
route is added/removed without updating the spec (TASK-WEB-016).
**Related:** [conversation contract ADR-0021](adrs/ADR-0021-conversation-backend-answer-contract.md),
[target voice path ADR-0002](adrs/ADR-0002-pipecat-gradium-target-voice-path.md),
[voice journey timing](../observability/voice-journey-timing.md).

## Server

```bash
cd voice-agent
python3 -m web_voice.server \
  --host 127.0.0.1 --port 8090 \
  --provider {fixture|gradium} \
  --runtime {pipecat|stdlib} \
  --backend {stub|http} \
  --webrtc {auto|on|off} \
  --stt-mode {streaming|batch} \
  --tts-mode {streaming|batch}
```

| Flag | Env | Default | Meaning |
|---|---|---|---|
| `--provider` | — | `gradium` | STT/TTS provider: `fixture` (offline) or `gradium` (live) |
| `--runtime` | `VOICE_RUNTIME` | `pipecat` | Voice runtime: `pipecat` (ADR-0002 target) or `stdlib` (fallback/comparison, ADR-0016) |
| `--backend` | `VOICE_BACKEND` | `stub` | Conversation backend: `stub` (deterministic offline) or `http` (real endpoint, see below) |
| `--webrtc` | — | `auto` | Streaming WebRTC signaling: `auto` (enable when the WebRTC runtime is importable), `on` (require it), `off` (disable). See the WebRTC section below. |
| `--stt-mode` | — | `streaming` | Streaming STT processor (partials + low-latency finalize) vs `batch` (aggregator + one-shot). Gradium only. |
| `--tts-mode` | — | `streaming` | Streaming TTS processor (incremental first-chunk playback) vs `batch` (whole-clip synthesis). Gradium only. |

Barge-in tuning (TASK-WEB-008) is env-only: `VOICE_BARGE_IN_THRESHOLD` (amplitude)
and `VOICE_BARGE_IN_FRAMES` (sustained-onset frame count); unset → processor
defaults apply.

End-of-call farewell (TASK-WEB-010, ADR-0035) is env-only on the WebRTC path:
`VOICE_FAREWELL_ENABLED` (`0`/`false` disables the feature), `VOICE_FAREWELL_PROMPT`
(confirmation question, default "Souhaitez-vous autre chose ?"),
`VOICE_FAREWELL_CLOSING` (spoken closing), `VOICE_FAREWELL_CONFIRM_TIMEOUT_S`
(bounded silence-as-confirmation window, default 6 s) and the FR phrase lists
`VOICE_FAREWELL_PHRASES` / `VOICE_FAREWELL_DONE_PHRASES` (comma-separated). On a
confirmed farewell the runtime emits a `voice.call_end` event with
`reason=customer_farewell` (vs `client_stop`/`client_drop` on a manual hangup/drop)
under the call correlation id. Unset → detector defaults apply.

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
- **Errors** are JSON with a stable `error_code`, a generic client-safe `message`
  and the `correlation_id` (TASK-WEB-006 / RF-013). The raw provider reason is
  **never** in the body — no audio, filesystem path, provider text or secret; the
  full sanitized reason stays server-side in the structured turn log, retrievable
  by `correlation_id` (mirrors the Java backend `ERR_UPSTREAM` pattern).
- Size guards: audio `> 25 MiB` → `413 {"error":"audio_too_large"}`; TTS text
  `> 5000` chars → `413 {"error":"text_too_large"}`.

## `POST /api/voice/stt` — transcribe

Voice-in only (no answer, no audio out).

- **Request:** body = PCM16 audio bytes; query = optional envelope ids.
- **200** (`SttOutcome.success`) — the full result JSON:

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

- **502** (`failed` or `unavailable`) — the client-safe error body only
  (TASK-WEB-006): no transcript is invented, and no raw provider text is echoed.

```json
{
  "outcome": "failed",
  "error_code": "stt_error",
  "correlation_id": "…",
  "message": "The voice service could not process this request. Please try again."
}
```

## `POST /api/voice/tts?text=…` — synthesize

Voice-out only.

- **Request:** `text` query param (URL-encoded); query = optional envelope ids.
- **200:** `audio/wav` body (the spoken text).
- **502:** the client-safe error body on failure/unavailable (TASK-WEB-006):

```json
{
  "outcome": "failed",
  "error_code": "tts_error",
  "correlation_id": "…",
  "message": "The voice service could not process this request. Please try again."
}
```

Empty text is reported `unavailable` (not a failure, `error_code: empty_text`) and
invents no audio.

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

- **502 (JSON), fails closed** when the loop cannot produce audio — the client-safe
  error body (`outcome`, `error_code`, `correlation_id`, `message`), never raw
  provider text (TASK-WEB-006):
  - STT did not succeed → `error_code` = the STT failure code, or `no_transcript`.
  - TTS produced no audio → `error_code` = the TTS failure code, or `no_audio`.

### Degraded mode (TASK-WEB-003-F)

When the backend is unavailable, not confident, or returns an empty answer, the
turn does **not** fail: it speaks a **safe fallback** (no invented billing
content, DEC-002) and returns **200** with `X-Answer-Outcome: degraded` and a
sanitized `X-Answer-Degraded-Reason`. Only an empty transcript (nothing to answer)
stays silent by design. See ADR-0021.

## `POST /api/voice/webrtc/offer` — streaming WebRTC signaling (Sprint 6)

The streaming Voice2Voice loop (ADR-0002 target) runs over a WebRTC media session
instead of the batch `/turn` request. This endpoint is the SDP offer→answer
signaling seam; media (audio in/out, 16 kHz Opus) then flows over the peer
connection, not over HTTP. Signaling is driven directly on `SmallWebRTCConnection`
(`web_voice/webrtc_signaling.py`) so the stdlib HTTP server needs no FastAPI.

- **Request:** JSON body from the browser/headless client:

```json
{ "sdp": "v=0…", "type": "offer", "pc_id": "…", "restart_pc": false }
```

`pc_id` + `restart_pc` are present only on renegotiation of an existing peer
connection; a first offer omits them.

- **200:** the SDP answer plus the session correlation id:

```json
{ "sdp": "v=0…", "type": "answer", "correlation_id": "…" }
```

- One `ChannelEnvelope` + one `TelemetryRecorder` are created **per connection**, so
  every turn in a call shares **one correlation id** (TASK-WEB-007). Media only
  starts once the pipeline `StartFrame` triggers `connection.connect()`.
- **Availability:** requires the WebRTC runtime (`pipecat` + `aiortc` / small-webrtc
  extras). With `--webrtc auto` the route is registered only when the runtime is
  importable; `--webrtc off` disables it; `--webrtc on` fails startup if unavailable.
- Static browser client: `web_voice/static/webrtc.html` + `webrtc.js`.

**Streaming turn behavior:** end-of-turn is detected frame-by-frame
(`StreamingEndOfTurnDetector`); partial transcripts stream during speech; the answer
audio starts on the first synthesized chunk; a barge-in (customer speaks while the
bot speaks) cancels playback via an `InterruptionFrame` (TASK-WEB-008). On call end
or drop a trailing partial utterance is drained before teardown.

## Telemetry

Every batch call emits OpenTelemetry-style spans on a per-request
`TelemetryRecorder` sharing one correlation id: `web.voice.ingress`,
`voice.end_of_turn`, `stt.request`, `backend.first_token` + `backend.request`,
`voice.tts.first_audio`, `web.voice.egress`. These feed the six US-036 slices
(see [voice-journey-timing](../observability/voice-journey-timing.md)). Degraded
turns carry `outcome=degraded`, `degraded=true` and the sanitized
`degraded_reason`/`error_code` (lengths only for any text).

**Streaming WebRTC calls** emit their telemetry differently: there is no HTTP
response per turn, so on session teardown the runtime prints one JSON telemetry
line (`{"spans": [...], "events": [...], "metrics": [...]}`) to stderr for the whole
call. On this path `web.voice.ingress` / `web.voice.egress` are not emitted (batch
HTTP only); the streaming turns carry `voice.end_of_turn`, `stt.request`,
`backend.first_token` + `backend.request` and `voice.tts.first_audio`, plus the
`stt.time_to_first_partial_ms` / `stt.time_to_final_ms` /
`tts.time_to_first_audio_ms` / `tts.time_to_last_audio_ms` metrics and
`voice.barge_in.count`. `scripts/streaming_latency_report.py` aggregates these into
the per-slice + `time_to_first_audio` composite report (TASK-WEB-009).
