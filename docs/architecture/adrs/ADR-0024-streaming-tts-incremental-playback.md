# ADR-0024: Streaming TTS Incremental Playback

## Status

Accepted (Sprint 6, TASK-WEB-004)

## Context

The Sprint 3/4 TTS path is **batch**: the answer text is synthesized in one call
(`GradiumTtsProvider.synthesize`) that collects every `audio` chunk from Gradium's
WebSocket TTS until `end_of_stream`, then plays the whole clip. The ST-1 spike
(`docs/qa/gradium-tts-contract.md`) measured the batch cost for a 53-char FR
sentence: **first chunk ~340 ms, whole clip ~1.59 s** (53 chunks, ~4.24 s of audio).
Waiting for the full synthesis before playback adds ~1.6 s to the perceived
response latency on top of the STT tail — unacceptable for a natural voice loop
(US-036, DEC-010, ADR-0018 pilot target `time_to_first_audio` p95 < 800 ms).

The Gradium TTS WebSocket already streams audio incrementally; the batch provider
simply buffers it. TASK-WEB-004 exposes that streaming so playback starts on the
first chunk. It pairs with streaming STT (TASK-STT-010, ADR-0023) to keep the whole
loop conversational.

## Decision

Add a **streaming TTS path** over the Gradium WebSocket, alongside the batch
provider (kept for the HTTP `/api/voice/tts|turn` endpoints, fixtures/offline dev,
and as the fallback).

1. **Transport = WebSocket, incremental.** New async seam in
   `tts_synthesis/streaming.py`: `GradiumStreamingTtsProvider` opens a
   `GradiumStreamingTtsSession` per turn. `synthesize(text)` sends the text +
   `end_of_stream`; `stream()` is an async iterator that yields `AudioChunk`s as
   they arrive and returns on the terminal `end_of_stream`. The WebSocket is
   injected via a duck-typed `Connector`, so unit tests use a fake socket (no
   network) and the API key travels only in the connect header, never in a frame,
   log or telemetry attribute. Server `error`, an unparsable frame or a stalled
   socket surface as a safe `StreamingTtsError`.
2. **A dedicated streaming frame processor owns the TTS stage.**
   `web_voice/streaming_tts_processor.py` (`StreamingTtsProcessor`) consumes a plain
   `TextFrame` (the answer), opens the WS, and pushes each `TTSAudioRawFrame` as it
   streams so the transport plays it incrementally. It **replaces** the batch
   `TtsFrameProcessor` on the streaming path; the batch processor remains the
   fallback. It lives in `web_voice` (the WebRTC composition layer), keeping the
   transport-agnostic `voice_pipeline` TTS service free of the streaming wiring per
   the architecture-separation test. Synthesis is an **allowlist**
   (`type(frame) is TextFrame`), not a denylist: only a *plain* answer `TextFrame` is
   spoken, and every `TextFrame` subclass (`TranscriptionFrame` +
   `InterimTranscriptionFrame` = STT output, and any future subclass) is forwarded
   untouched — safe-by-default so a new subclass can never leak into synthesis and make
   the bot speak the customer's own words back (the regression that motivated the
   exact-type check).
3. **Safety invariants preserved (mirror of the batch runner).** A non-success
   outcome never invents audio: empty text → `UNAVAILABLE` (`empty_text`); a
   connect/handshake failure at `provider.open()` (auth/credit rejection, unreachable
   host, drop) or a mid-stream provider error → `FAILED` with a sanitized
   `tts.failure`; text present but zero chunks → `UNAVAILABLE` (`no_audio`). In every
   non-success case nothing flows downstream and no secret is exposed. A stalled socket
   surfaces as `FAILED` within a conversational per-chunk budget
   (`DEFAULT_CHUNK_TIMEOUT_S = 8 s`) rather than freezing the turn.
4. **Wiring is configurable.** `StreamingVoiceSession` accepts an injected
   `tts_processor`; `WebRtcSignalingService` builds the streaming TTS processor when
   a streaming TTS provider is present (independent of the STT mode, so it applies to
   both the streaming-STT and batch-STT sessions); `server.py` gains
   `--tts-mode {streaming,batch}` (default `streaming`, Gradium-only) with
   `build_streaming_provider`.
5. **Telemetry.** The `tts_first_audio` slice keeps the `voice.tts.first_audio` span
   (same name the batch runner emits, so US-036's `pipeline_timing` needs no change),
   with **span duration = time-to-first-audio**. The processor adds
   `tts.time_to_first_audio_ms` and `tts.time_to_last_audio_ms` metrics (+ a
   `tts.audio.final` event carrying the chunk count) so the streaming win is visible
   per turn.

## Consequences

**Positive**

- Customer-perceived TTS start cut ~3.4x (live: `voice.tts.first_audio` ~435–515 ms,
  median ~463 ms, vs ~1.59 s whole-clip batch synthesis). Playback begins on the
  first chunk; the rest streams while the customer already hears the answer.
- No new dependency (`websockets` is transitive via Pipecat); the batch provider and
  the stdlib/fixture path keep their contract.
- Key hygiene, safe-failure (no invented audio) and STT/TTS separation preserved.

**Negative / risks**

- A WebSocket per turn adds connection setup/teardown; acceptable given the win.
  Socket reuse/multiplexing across turns is a future optimization (shared with the
  streaming-STT note in ADR-0023).
- The `web.voice.egress` slice is still not measured on the WebRTC path (the
  transport sends frames itself; no `record_egress` hook). Out of scope for this
  ticket; the end-to-end `time_to_first_audio` close is TASK-WEB-009.
- Barge-in (US-021, TASK-WEB-008) needs to cancel an in-flight `stream()` iterator;
  the async-iterator + `aclose()` design supports it but the interrupt wiring is a
  separate ticket.

**Neutral**

- Provider agnosticism unchanged: streaming TTS sits behind the same provider seam;
  only Gradium has a streaming variant today, others fall back to batch.

## Alternatives considered

- **Keep batch TTS and just start playback earlier client-side:** rejected — the
  server still synthesizes the whole clip before sending, so the first-audio cost
  stays ~1.6 s; the win requires streaming the chunks off the WebSocket as they
  arrive.
- **Chunk the text and issue several batch calls:** rejected — adds per-call
  handshakes and prosody seams; the WebSocket already streams within one call.
- **Reuse one WebSocket across turns (multiplexing):** deferred — a
  latency/footprint optimization; per-turn sockets are simpler and already meet the
  first-audio target.
- **Realtime single-vendor voice API:** rejected by ADR-0012 (modular STT/LLM/TTS
  over a monolithic realtime API).
