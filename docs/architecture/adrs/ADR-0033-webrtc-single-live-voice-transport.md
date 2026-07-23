# ADR-0033: WebRTC Is The Single Live Voice Transport (WebSocket Server↔Provider Only, Batch `/turn` Offline/Tests)

## Status

Accepted — builds on [ADR-0022](ADR-0022-webrtc-transport-for-streaming-voice-loop.md)
(WebRTC transport for the streaming loop) and clarifies the client-facing transport
boundary left implicit there. Reaffirms [ADR-0002](ADR-0002-pipecat-gradium-target-voice-path.md),
[ADR-0012](ADR-0012-modular-voice-pipeline-over-realtime-api.md),
[ADR-0025](ADR-0025-barge-in-native-interruption.md), and the latency framing of
[ADR-0029](ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md).

## Context

The voice-agent web runtime exposes two client entry points to the same conversation
backend:

1. **WebRTC path** (`web_voice`, ADR-0022): the browser opens a peer connection,
   streams mic PCM in, drives streaming STT, and receives **streaming TTS** frame by
   frame. Measured **time-to-first-audio ≈ 360 ms** with gradual playback; barge-in
   works because the browser's `getUserMedia({echoCancellation: true})` removes most of
   the speaker→mic echo (the AEC that TASK-WEB-008 / ADR-0025 depend on).
2. **Batch HTTP `/turn` path**: the client uploads a complete utterance, the server runs
   STT → answer → **batch TTS**, and returns one audio blob. There is no incremental
   audio delivery, so time-to-first-audio equals full synthesis time (**≈ 14 s** for a
   long grounded answer). This path predates the streaming work and is what was
   colloquially called "the WebSocket path" in earlier discussions.

A recurring question was whether to add a **WebSocket transport to the browser** so the
batch path could stream audio like WebRTC, and whether such a WebSocket path would be a
better live transport than WebRTC. Two structural facts settle it:

- **Streaming audio requires a streaming transport, not the batch `/turn` request.**
  `/turn` is a single request/response; making it stream would mean replacing it with a
  bidirectional transport — i.e. building a second live transport next to WebRTC. The
  streaming TTS processor already exists only on the WebRTC path.
- **A browser-facing WebSocket has no acoustic story of its own.** WebRTC gives us the
  media stack for free: browser-native **echo cancellation, noise suppression, jitter
  buffering, and Opus**. A raw WebSocket carrying PCM does none of this; we would have to
  re-implement AEC (or accept that barge-in self-interrupts without headphones, the exact
  failure ADR-0025 point 7 documents). WebSocket does not beat WebRTC for a live
  mouth-to-ear voice loop — it strictly loses the media features WebRTC provides.

WebSocket **is** the right transport in one place: **server↔provider** streaming (the
voice-agent ↔ Gradium STT/TTS sockets), where there is no microphone, no echo path, and
we want a simple framed byte stream. That usage is unaffected by this decision.

## Decision

1. **WebRTC is the single live (customer-facing) voice transport** for the web channel.
   All real-time voice turns — streaming STT in, streaming TTS out, barge-in — go through
   the `web_voice` WebRTC path. New live-voice features target WebRTC.

2. **Do not add a browser-facing WebSocket voice transport.** It would duplicate the live
   path, carry no native AEC/noise-suppression/jitter handling, and provide no latency or
   quality advantage over WebRTC. If a non-WebRTC live transport is ever required (e.g. a
   constrained embedded client), it needs its own ADR justifying the loss of the browser
   media stack.

3. **WebSocket stays the server↔provider streaming transport.** The voice-agent ↔ Gradium
   STT/TTS sockets remain WebSocket; this ADR does not touch them.

4. **The batch HTTP `/turn` path is offline/testing only.** It is retained for
   deterministic fixtures, QA/behave runs, latency micro-benchmarks, and non-interactive
   integration — never as a production live-voice path (its ≈ 14 s time-to-first-audio is
   not a conversational experience). It is not deprecated or removed; its scope is fixed
   to non-interactive use.

## Consequences

- The live-voice surface has **one** transport to instrument, test, and optimize (WebRTC),
  keeping the ADR-0029 mouth-to-ear latency work and the ADR-0025 barge-in work on a single
  path instead of two divergent ones.
- Streaming TTS effort (TASK-WEB-004) and its ≈ 360 ms first-audio gain stay concentrated
  where they are delivered; no parallel streaming stack is built for `/turn`.
- The batch `/turn` path keeps its value as a stable, fully-deterministic harness for tests
  and per-slice latency measurement without pretending to be a live channel.
- Telephony/Genesys ingress (future EPIC-010 / Sprint 10) enters through its own media layer
  and is **out of scope** here; this ADR governs the **web** client transport only and does
  not pre-decide the telephony media path.
- No change is required to server↔provider sockets, the backend HTTP conversation contract
  (ADR-0021), or the modular cascade (ADR-0012).

## Alternatives Considered

- **Add a WebSocket voice transport to the browser and stream `/turn` audio over it:**
  rejected — it duplicates the WebRTC live path and drops browser-native AEC / noise
  suppression / jitter buffering / Opus, reintroducing the barge-in self-interruption
  problem (ADR-0025 point 7). No latency or quality upside over WebRTC.
- **Make batch `/turn` the primary live path and accept high first-audio latency:** rejected
  — ≈ 14 s time-to-first-audio is not conversational and is incompatible with the ADR-0029
  latency criterion.
- **Drop the batch `/turn` path entirely:** rejected — it is the deterministic harness for
  fixtures, QA/behave, and per-slice latency benchmarks; removing it would cost test
  reproducibility for no runtime benefit.
- **Move the live loop to a speech-to-speech provider (transport becomes provider-owned):**
  out of scope and already rejected for V1 by ADR-0012 / ADR-0029 (surrenders RAG, DEC-002,
  guardrail, and memory control).

## Related Documents

- [ADR-0022 — WebRTC transport for the streaming voice loop](ADR-0022-webrtc-transport-for-streaming-voice-loop.md)
- [ADR-0002 — Pipecat + Gradium target voice path](ADR-0002-pipecat-gradium-target-voice-path.md)
- [ADR-0012 — Modular voice pipeline over realtime API](ADR-0012-modular-voice-pipeline-over-realtime-api.md)
- [ADR-0018 — Voice latency targets and SLO measurement](ADR-0018-voice-latency-targets-and-slo-measurement.md)
- [ADR-0021 — Conversation backend answer contract](ADR-0021-conversation-backend-answer-contract.md)
- [ADR-0025 — Barge-in native interruption](ADR-0025-barge-in-native-interruption.md)
- [ADR-0029 — Pilot latency criterion with a real backend](ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md)
- TASK-WEB-004 (streaming TTS), TASK-WEB-007 (WebRTC transport), TASK-WEB-008 (barge-in)
