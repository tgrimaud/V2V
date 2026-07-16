# TASK-STT-010 — Streaming STT provider-capability spike

**Ticket:** TASK-STT-010 (Stream partial STT transcripts to cut perceived latency)
**Related:** RF-007 (chunked/streaming ingress), US-036 (`stt` slice latency), DEC-005
**Date:** 2026-07-16
**Branch:** `task/TASK-STT-010-streaming-stt`
**Tool:** `voice-agent/scripts/gradium_stt_stream_spike.py`

## Why a spike first

The sprint flagged an open question — *"confirm Gradium streaming ASR tokens"* — and
RF-007 noted the current ingress reads a fixed `Content-Length` body and would need a
chunked/streaming transport. The whole TASK-STT-010 design (transport, provider seam,
turn-finalization) depends on whether Gradium supports live streaming ASR. Following
the Sprint 3 TTS discipline ("live spike first to confirm the real contract before
building the provider"), we probed the live endpoint before writing any provider code.

## Finding: Gradium exposes a WebSocket streaming ASR

- Endpoint: `wss://api.gradium.ai/api/speech/asr`, auth via `x-api-key` header.
- Lifecycle: client sends `setup` (first message) → server `ready` → client streams
  `{"type":"audio","audio":"<base64 pcm>"}` frames → server streams `text` (partials,
  with `start_s`), `step` (semantic VAD every 80 ms, `inactivity_prob`), `end_text`
  (`stop_s`) → client sends `flush`/`end_of_stream` → server `flushed` then
  `end_of_stream`.
- Input formats include `pcm_16000` (our capture format). `json_config` carries
  `language`, `delay_in_frames`, etc. — identical shape to the batch REST provider.
- The Python `websockets` and `aiohttp` clients are **already present** in the venv
  (transitive via Pipecat) — no new dependency is required.

## Live measurement (real key, `fixtures/long/invoice-breakdown.pcm`, 5.45 s)

Audio streamed in 1920-sample (~120 ms) frames, real-time paced to emulate a live mic.

| Metric | Streaming | Batch baseline (web-voice QA) |
| --- | --- | --- |
| Utterance length | 5.45 s | — |
| Time-to-first-partial | **1.44 s** (during speech) | n/a (no partials) |
| Time-to-final (from stream start) | 6.40 s | — |
| **Post-end-of-turn tail** (customer-perceived) | **0.78 s** | ~3.4 s (extrapolated from 2.7 s @ 4.3 s) |

Transcript: `"vous m'expliquer en détail les différentes lignes qui composent le
montant total de ma facture?"` — matches the reference except the first word
`Pouvez` was clipped.

## Design implications for the implementation

1. **Transport = WebSocket** (`wss://.../api/speech/asr`) using stdlib-adjacent
   `websockets` (already available). Batch REST provider stays for fixtures/offline.
2. **The win is the tail**, not the total: streaming removes the "process the whole
   clip after upload" cost, cutting the customer-perceived post-speech wait ~4×.
3. **Turn finalization**: our energy-based end-of-turn (TASK-STT-012) drives the
   `flush` + `end_of_stream`; Gradium's own `step` VAD is available as a future
   alternative but is out of scope here (TASK-STT-009 owns detection).
4. **Warmup clipping**: `delay_in_frames=10` (~800 ms) means the first ~0.7 s of
   audio is consumed as context; the first word can be dropped. Mitigation during
   integration: feed the aggregator's pre-speech lead-in buffer into the stream, and
   evaluate `delay_in_frames` / `padding_bonus` tuning. Track as a quality check.
5. **Telemetry**: expose `time_to_first_partial` and `time_to_final` separately on
   the `stt` slice so US-036 reports both.
6. **Provider seam** must be async (WebSocket) and emit partial + final results;
   the batch `SttProvider.transcribe(path) -> str` contract stays untouched.

## Next steps (implementation)

- Async streaming STT provider seam + `GradiumStreamingSttProvider` with an
  injectable WS transport (fake for offline unit tests).
- Streaming `SttFrameProcessor` that feeds chunks to the WS and emits interim/final
  `TranscriptionFrame`, finalizing on the TASK-STT-012 end-of-turn.
- ADR for the streaming STT transport decision; move RF-007 to Closed on landing.
