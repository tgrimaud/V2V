# ADR-0025: Barge-in via Native Pipecat Interruption + Existing Streaming VAD

## Status

Accepted (Sprint 6, TASK-WEB-008)

## Context

The streaming loop (ADR-0022/0023/0024) plays the answer incrementally, but until
now the customer had to wait for the bot to finish before speaking: incoming mic
frames were still buffered while the bot spoke (`UtteranceAggregator` scope guard),
so controlled demos needed headphones to avoid the bot echoing into its own
aggregator. US-021 (Sprint 6 acceptance) requires **barge-in**: the customer can
interrupt the spoken answer and be heard immediately.

Barge-in has two halves:

- a **policy** — *when* to interrupt (the customer started speaking while the bot
  was speaking); and
- a **mechanism** — *how* to stop playback and cancel the in-flight synthesis.

Two design questions had to be answered before implementing:

1. **Which VAD drives onset detection?** The project already ships an energy-based
   `StreamingEndOfTurnDetector` (TASK-STT-012), validated live for end-of-turn.
   Pipecat also bundles a neural `SileroVADAnalyzer` (`pipecat.audio.vad.silero`,
   backed by `onnxruntime`).
2. **How does interruption propagate?** The runtime is already a real Pipecat
   pipeline on `SmallWebRTCTransport` (ADR-0022), so the framework's own interruption
   primitives are available.

Investigation of the installed **pipecat 1.5.0** established the facts that shape
this decision:

- `FrameProcessor` handles `InterruptionFrame` (a `SystemFrame`, processed
  out-of-band) natively: on receipt it **cancels and re-creates its process task**,
  so an in-flight `process_frame` (e.g. a streaming `StreamingTtsProcessor`
  synthesis) is cancelled via `asyncio.CancelledError`.
- The base **output transport** flushes its buffered audio and stops playback on an
  `InterruptionFrame` (`handle_interruptions`), and it emits
  `BotStartedSpeakingFrame` / `BotStoppedSpeakingFrame` **both downstream and
  upstream** as it plays / stops the bot audio.
- `FrameProcessor.broadcast_interruption()` sends an `InterruptionFrame` upstream and
  downstream.
- There is **no** `vad_analyzer` field on `TransportParams` and **no** consumer of a
  `VADAnalyzer` anywhere in the 1.5.0 transports: the framework provides the
  interruption *mechanism* but not an auto-wired VAD *policy*. `SileroVADAnalyzer`
  exists only as a standalone `analyze_audio(pcm) -> VADState` component that a
  caller must drive by hand — the same integration effort as our own detector.

## Decision

Implement barge-in in the **voice runtime** (the correct boundary — the runtime owns
turn detection and barge-in), reusing Pipecat's native interruption mechanism and
our existing VAD for the policy.

1. **Policy = existing energy VAD, gated by bot-speaking state.**
   `StreamingSttProcessor` tracks `_bot_speaking` from the
   `BotStartedSpeakingFrame` / `BotStoppedSpeakingFrame` the output transport emits
   upstream. On **speech onset** (the once-per-turn moment it opens the provider
   session because `StreamingEndOfTurnDetector` reports speech) **while the bot is
   speaking**, it calls `broadcast_interruption()`. Firing is guarded to once per
   turn (the session-open onset) and clears `_bot_speaking` so a stale flag cannot
   re-trigger before the `BotStoppedSpeakingFrame` arrives. The barge-in utterance is
   then captured normally as the new turn.

2. **Mechanism = native `InterruptionFrame`.** `broadcast_interruption()` flushes the
   output transport's buffered audio (playback stops promptly) and cancels the
   `StreamingTtsProcessor` task. The TTS processor's synthesis is made
   **interruptible**: on `CancelledError` it reports an `interrupted` outcome
   (`tts.interrupted` event) and always releases the WebSocket via a `finally`
   (best-effort `_safe_aclose`) so an interrupted turn does not leak the connection,
   then re-raises so the framework completes the interruption cleanly.

3. **Silero is deferred, not adopted.** Because Silero is a manual, standalone
   component in 1.5.0 (no auto-wiring), adopting it would be the *same* integration
   surface as our detector — only a better verdict function (neural vs energy
   threshold), at the cost of an `onnxruntime` model dependency and divergence from
   the live-validated TASK-STT-012 detector. We keep the existing detector for onset
   and reserve Silero as a **drop-in verdict upgrade** if live testing shows too many
   false barge-ins that echo cancellation (below) cannot fix.

4. **Graceful drain on call end (slice 1).** `StreamingVoiceSession.drain()` queues an
   `EndFrame` on a graceful `closed`/`disconnected` event so a trailing partial
   utterance (customer mid-speech at hangup) is still finalized instead of silently
   dropped; wired from `WebRtcSignalingService` cleanup.

5. **Echo cancellation is a required companion (slice 3).** Without browser-side
   `echoCancellation`, the bot's own audio re-enters the mic and the energy detector
   treats it as speech → self-interruption. The WebRTC client must set
   `echoCancellation` (and `noiseSuppression` / `autoGainControl`) on `getUserMedia`.
   **Barge-in must not be validated live before slice 3 lands.**

6. **Observability.** `voice.barge_in.detected` event + `voice.barge_in.count` metric
   (correlation id, channel, provider) on detection; `tts.interrupted` event
   (`audio_chunks`, `elapsed_ms`) on the cut synthesis. The `voice.tts.first_audio`
   span is emitted for an interrupted turn **only if audio actually played**, carrying
   the real time-to-first-audio (never total elapsed), so barge-in turns never skew
   the `tts_first_audio` p95 the sprint measures.

## Consequences

**Positive**

- No new runtime dependency: barge-in rides Pipecat's native interruption; onset uses
  the already-validated energy detector.
- Playback stops on the native output flush; the barge-in utterance continues as the
  next turn with no extra plumbing.
- Safety/observability invariants preserved: no leaked WebSocket, sanitized outcomes,
  correlation-id continuity, no customer text/audio in events.

**Negative / risks**

- Onset gating depends on the output transport emitting `BotStarted/StoppedSpeaking`
  upstream. Confirmed statically in pipecat 1.5.0; validated end-to-end only by the
  Behave/live pass (not unit tests, which inject the frames).
- Reaction latency (onset → playback stop) is not yet measured in-process (the flush
  happens in the transport); a reaction span is deferred to the QA/latency slice
  (TASK-WEB-009).
- `broadcast_interruption()` resets the STT process queue; a few ms of queued
  leading audio for the barge-in utterance may be dropped. Acceptable; observed
  benign in tests.
- Best-effort close: a re-cancellation during `aclose()` may drop rather than cleanly
  close the socket (the provider reaps it on drop).

**Neutral**

- Provider/VAD agnosticism unchanged: onset detection sits behind the injected
  `StreamingEndOfTurnDetector`; swapping in Silero later changes only the verdict,
  not the barge-in wiring.

## Alternatives considered

- **Adopt Silero VAD now (neural onset):** rejected for this ticket — in pipecat
  1.5.0 it is a manual standalone component (same integration effort as our detector,
  no native auto-wiring), adds an `onnxruntime` model dependency, and diverges from
  the live-validated TASK-STT-012 detector. Kept as a drop-in verdict upgrade if
  false barge-ins persist after echo cancellation.
- **Custom interruption signalling (bespoke flush + cancel):** rejected — Pipecat's
  `InterruptionFrame` already flushes the output buffer and cancels in-flight tasks
  natively; a bespoke path would reimplement framework behaviour and fight the
  pipeline.
- **Fire barge-in on every speech onset (ungated):** rejected — interrupting when the
  bot is not speaking disrupts normal turns and adds telemetry noise; gate on
  `_bot_speaking`.
- **Gate onset with an N-frame confirmation before interrupting:** deferred — a
  possible false-trigger hardening; start with the single-frame onset (fast cut) and
  rely on echo cancellation + amplitude threshold, add confirmation only if live
  testing needs it.
