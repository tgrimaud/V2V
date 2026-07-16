# ADR-0023: Streaming STT Transport And Turn Finalization

## Status

Accepted (Sprint 6, TASK-STT-010)

## Context

The Sprint 4/5 STT path is **batch**: the WebRTC utterance aggregator buffers a whole
turn and, on end-of-turn, transcribes it in one REST call
(`POST https://api.gradium.ai/api/post/speech/asr`). Live QA measured that this call's
latency scales with utterance length — ~2.3 s for a 3.4 s clip, ~2.7 s for 4.3 s —
because the server processes the whole clip *after* upload. That cost lands entirely
**after** the customer stops speaking, which is exactly the perceived-latency tail we
must cut for a natural voice loop (US-036, RF-007, DEC-010).

RF-007 flagged that the ingress reads a fixed `Content-Length` body and would need a
chunked/streaming transport. Sprint 6 opened TASK-STT-010 with a provider-capability
spike (`docs/qa/stt-010-streaming-stt-spike.md`) to lock the contract before building.

Key facts discovered by the spike:

- Gradium exposes a **WebSocket streaming ASR** at `wss://api.gradium.ai/api/speech/asr`
  (`x-api-key` auth): client sends `setup` → server `ready` → client streams
  `{"type":"audio","audio":"<base64 pcm>"}` → server streams `text` (partials),
  `step` (semantic VAD every 80 ms), `end_text` → client sends `flush`/`end_of_stream`.
- Streaming the audio *during speech* drops the customer-perceived **post-end-of-turn
  tail to ~0.78 s** (vs ~3.4 s batch) — a ~4× cut — because most audio is already
  processed by the time the turn ends.
- `websockets` (and `aiohttp`) are already present transitively via Pipecat — **no new
  dependency**.
- Gradium has its own semantic VAD (`step`), but end-of-turn ownership is TASK-STT-009's
  concern; TASK-STT-010 consumes an end-of-turn signal, it does not redefine it.

## Decision

Add a **streaming STT path** over the Gradium WebSocket, alongside the batch REST
provider (kept for fixtures/offline dev and as the fallback).

1. **Transport = WebSocket.** New async seam in `stt_validation/streaming.py`:
   `GradiumStreamingSttProvider` opens a `GradiumStreamingSession` per turn. The
   WebSocket is injected via a duck-typed `Connector`, so unit tests use a fake socket
   (no network) and the API key travels only in the connect header, never in a frame,
   log or telemetry attribute. Server error / mid-turn drop surface as a safe
   `StreamingSttError`.
2. **Turn finalization stays deterministic.** The validated frame-incremental
   `StreamingEndOfTurnDetector` (TASK-STT-012) drives finalization: on end-of-turn the
   processor sends `flush` + `end_of_stream` and awaits the final transcript. Gradium's
   own `step` VAD is **not** used as the turn boundary in V1 (keeps one authoritative,
   testable end-of-turn owner; revisit as a future enhancement).
3. **A dedicated streaming frame processor owns the STT stage.**
   `web_voice/streaming_stt_processor.py` (`StreamingSttProcessor`) consumes continuous
   `InputAudioRawFrame`, opens the WS **only once speech starts** (`detector.has_speech`,
   so inter-turn silence is not streamed), pushes `InterimTranscriptionFrame` partials
   as they arrive, emits the `voice.end_of_turn` span, and on end-of-turn emits the
   final `TranscriptionFrame`. It **replaces** the `[UtteranceAggregator ->
   SttFrameProcessor]` pair on the streaming path; the batch pair remains the fallback.
   It lives in `web_voice` (the WebRTC composition layer that legitimately wires both
   the detector and the STT provider), keeping `voice_pipeline` services free of the
   streaming wiring per the architecture-separation test.
4. **Wiring is configurable.** `StreamingVoiceSession` accepts an injected
   `stt_processor`; `WebRtcSignalingService` builds the streaming path when a streaming
   provider is present; `server.py` gains `--stt-mode {streaming,batch}` (default
   `streaming`, Gradium-only) with `build_streaming_provider`.
5. **Telemetry.** The `stt` slice keeps the `stt.request` span (duration = the
   post-end-of-turn tail = `time_to_final`); the processor adds `time_to_first_partial`
   and `time_to_final` (record + metrics) so US-036 reports both.

## Consequences

**Positive**

- Customer-perceived STT tail cut ~4× (live: `stt.request` 818 ms vs ~3.4 s batch);
  partials available during speech. Closes RF-007 (streaming ingress transport).
- No new dependency; batch REST provider and stdlib/fixture path keep their contract.
- Key hygiene, safe-failure and single-owner end-of-turn preserved.

**Negative / risks**

- A WebSocket per turn adds connection setup/teardown; acceptable given the tail win.
  Socket reuse/multiplexing across turns is a future optimization.
- **First-word warmup clipping:** Gradium's `delay_in_frames` (~800 ms context) can drop
  the leading word (spike: `Pouvez` dropped). Mitigation deferred: feed a short
  pre-speech lead-in and/or tune `delay_in_frames`/`padding_bonus` — tracked as a QA
  quality follow-up, not a blocker for the latency objective.
- Gradium's semantic `step` VAD is left unused in V1 (deliberate — one end-of-turn
  owner); a future ticket may evaluate it against the energy detector.

**Neutral**

- Provider agnosticism unchanged: streaming STT sits behind the same provider seam;
  only Gradium has a streaming variant today, others fall back to batch.

## Alternatives considered

- **Response-streaming the batch REST call** (read NDJSON incrementally while uploading
  the whole clip): rejected — audio is still uploaded after end-of-turn, so the
  clip-length processing cost remains; it does not cut the tail.
- **Use Gradium's semantic `step` VAD as the turn boundary:** deferred — would split
  end-of-turn ownership away from the validated TASK-STT-009/012 detector; revisit as an
  enhancement once compared head-to-head.
- **Reuse one WebSocket across turns (multiplexing):** deferred — a latency/footprint
  optimization; per-turn sockets are simpler and already meet the tail target.
- **Realtime single-vendor voice API:** rejected by ADR-0012 (modular STT/LLM/TTS over a
  monolithic realtime API).
