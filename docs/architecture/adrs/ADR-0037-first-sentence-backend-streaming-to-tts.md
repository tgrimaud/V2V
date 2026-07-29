# ADR-0037 — First-sentence backend answer streaming to TTS

- **Status:** Proposed (2026-07-29) — decision recorded now; implementation gated on
  the TASK-WEB-014 live baseline (optimize against a measured baseline, not blind)
- **Deciders:** Architecture + Product (DEC-002 billing-safety owner)
- **Related:** TASK-WEB-015 (perceived-latency levers), TASK-WEB-014 (mouth-to-ear
  measurement — prerequisite), ADR-0029 (pilot latency criterion & sub-targets),
  ADR-0012 (modular cascade reaffirmed for V1), ADR-0036 (backend↔runtime
  communication style — Flow A stays synchronous per turn), DEC-002 (no invented
  amounts), ADR-0034 (weak-confidence clarify)
- **Supersedes / touches:** none (extends the Flow A per-turn path of ADR-0036)

## Context

The Sprint 7 live baseline (see TASK-WEB-015) shows the backend `/converse` call is
the largest slice of time-to-first-audio (~1.1–1.2 s, warm): the voice runtime today
calls the **blocking** `POST /api/conversation/converse` through
`HttpBackendAdapter.answer()` and waits for the **complete** LLM answer before any
audio is synthesized (`backend.first_token == backend.request`). The backend already
exposes an **SSE streaming** endpoint (`GET /api/conversation/ask-stream`) that the
voice path does not use.

Lever 1 of TASK-WEB-015 proposes to consume that stream and hand the **first
sentence-sized chunk** to the streaming TTS as soon as it is ready, so first audio
starts on the first sentence (~200–400 ms of content) instead of the whole answer —
an estimated −700 to −900 ms every turn, moving `time_to_first_audio` toward the
ADR-0029 sub-target (p95 ≤ 1.2 s).

This is attractive but crosses a **billing-safety boundary** (DEC-002) and a
**latency-measurement dependency** (ADR-0029 / TASK-WEB-014), which is why the
decision is recorded before the implementation and the implementation is gated.

### Why this needs an ADR (the two hazards)

1. **DEC-002 — speaking before the verdict is settled.** Today the *full* answer,
   its grounding and its `confidence` all arrive together; the runtime's degraded /
   weak-confidence policy (ADR-0034) can still suppress or reframe the turn *before*
   any audio plays. If we speak the first sentence as tokens stream, we commit audio
   **before** the confidence/grounding verdict is known — a low-confidence or
   ungrounded first sentence could reach the caller and cannot be un-said. For a
   billing assistant that must never invent amounts, this is a regression risk, not a
   cosmetic one.
2. **Optimize against a real baseline, not blind.** ADR-0029 and TASK-WEB-014 make a
   live, per-slice mouth-to-ear baseline the prerequisite for any latency claim.
   Shipping lever 1 without a before/after live sample would be an unmeasured change
   to a latency feature.

## Decision

1. **Adopt first-sentence streaming as the target for lever 1**, on the **existing
   Flow A synchronous-per-turn path** (ADR-0036, no broker): the voice runtime
   consumes `GET /api/conversation/ask-stream` (SSE) and forwards the first
   **guardrail-passing, sentence-sized** chunk to the streaming TTS as a plain
   `TextFrame`, then continues with subsequent sentences. Valid for V1 because
   ADR-0012 reaffirms the modular cascade (OQ-005: V1 "OpenAI" = cascade chat
   provider, not Realtime speech-to-speech).

2. **DEC-002 safety contract for streamed chunks (non-negotiable).** A streamed
   sentence may be spoken **only if** the backend guarantees that streamed text is
   already grounded and the turn's confidence gate has passed at the point the chunk
   is emitted. Concretely, one of:
   - (a) the backend only starts streaming answer tokens **after** its grounding +
     confidence gate has passed (the SSE stream is "vetted-only"), emitting a
     terminal `done` event with the same `confidence`/agent metadata as `/converse`;
     **or**
   - (b) the SSE stream carries an early, authoritative `confidence`/grounding signal
     the runtime can honour before it speaks the first chunk.
   Until the backend SSE contract confirms (a) or (b) in writing, the runtime does
   **not** speak partial content. Absent that guarantee, first-sentence streaming is
   **not** DEC-002-safe and must not ship.

3. **Runtime seam.** The hook is the `AnswerProcessor` backend dispatch (same seam as
   the TASK-WEB-019 filler). A streaming backend port method (e.g.
   `answer_stream(request) -> Iterable[chunk]`) is added alongside the existing
   blocking `answer()`; the blocking path stays the default and the fallback. The
   streaming TTS stage already synthesizes each incoming `TextFrame` incrementally
   (TASK-WEB-004), so no TTS change is needed. Barge-in (TASK-WEB-008) already applies
   to any spoken `TextFrame`, so a streamed first sentence is interruptible unchanged.

4. **Feature-flagged and default-off until live-validated.** The behaviour ships
   behind an env flag, **off by default**, and is only enabled after: the DEC-002 SSE
   contract (point 2) is confirmed, a warm+cold **live** before/after sample with the
   real backend beats the TASK-WEB-014 baseline, and grounding/guardrail behaviour is
   verified unchanged.

## Consequences

- **Positive:** the largest latency slice is attacked directly; reuses the existing
  streaming TTS, barge-in and the `AnswerProcessor` seam; keeps Flow A synchronous
  (no broker, ADR-0036); the blocking path remains the safe default and fallback.
- **Negative / cost:** requires a backend SSE grounding/confidence contract (a
  cross-service dependency on the Java backend, not runtime-only); the streamed path
  is harder to reason about for the weak-confidence/degraded policy than a single
  vetted answer; needs a live before/after sample to claim the win.
- **Risk if rushed:** speaking an ungrounded/low-confidence first sentence (DEC-002
  regression). Mitigated by points 2 and 4 (vetted-only stream + default-off +
  live gate).

## Alternatives considered

- **Keep blocking `/converse` and rely only on the filler (TASK-WEB-019).** The
  filler improves *perceived* latency but does not reduce the real backend slice.
  Complementary, not a substitute.
- **Broker/async fan-out for the answer (Flow B).** Rejected for the per-turn live
  path in ADR-0036 (adds latency to a latency feature, RPC-over-broker correlation,
  ordering hazards). Reserved for async/omnichannel (Sprint 12).
- **Client-side sentence segmentation without a backend grounding guarantee.** The
  runtime cannot verify grounding, so it would risk DEC-002. Rejected.

## Lever 2 note (connect-time warm-up) — recorded here, not a separate ADR

Lever 2 (open a throwaway STT streaming session + fire a tiny LLM/embedding warm call
at WebRTC connect, symmetric to the TASK-WEB-011 TTS pre-warm) is **low-risk and
provider-agnostic** and needs no new architectural decision: it mirrors the accepted
`TtsSessionWarmer` lifecycle (open-at-connect, hand to the first turn, discard on
close, never leak). It is scheduled with the TASK-WEB-014 live pass because its payoff
(~−450 ms cold-start) is only measurable live. The STT-session pre-warm is
runtime-owned; the backend LLM/embedding warm call is a **backend** concern (needs a
backend warm endpoint) and is tracked as a backend follow-up, not shipped blind from
the runtime.

**Delivered (TASK-WEB-021, 2026-07-29).** The `TtsSessionWarmer` was extracted into a
provider-agnostic `SessionWarmer` (`web_voice/session_warmer.py`); `TtsSessionWarmer`
is now a thin subclass, so STT and TTS share one warmer with identical
open/acquire/aclose semantics. `StreamingSttProcessor` pre-opens a spare STT session at
`StartFrame`, hands it out on the first `_open_session` (a failed spare falls back to a
fresh on-demand open — never blocks the turn), and discards any unused spare on
`EndFrame`/`CancelFrame` (no leak). The backend warm call is wired from `AnswerProcessor`:
on `StartFrame` it fires `backend.warm_up()` once, off the critical path
(`asyncio.to_thread`), swallowing any fault (recorded as a `miss`, never blocks connect);
`HttpBackendAdapter.warm_up()` POSTs to the `/warm-up` sibling of the converse URL
(consuming TASK-BE-017), with a generous timeout since the cold call runs off-path.
Both are env-tunable: `VOICE_STT_PREWARM=0` and `VOICE_BACKEND_WARMUP=0` disable them.
Observability: `voice.backend.warmup` event + `voice.backend.warmup.count` metric carry
the correlation id, provider and `outcome` (`success`/`miss`). Still pending: a **live**
cold-vs-warm turn-1 sample (real backend with `/warm-up` reachable) to confirm the delta.

## Status of TASK-WEB-015 at this ADR

- **Lever 3 (end-of-turn hold tuning):** implemented (env-tunable
  `VOICE_END_OF_TURN_SILENCE_MS`, clamped to a 250 ms safe floor, default 500 ms) —
  offline, deterministic, testable now.
- **Lever 1 (this ADR):** designed + gated on the DEC-002 SSE contract and the
  TASK-WEB-014 live baseline (default-off feature flag).
- **Lever 2 (TASK-WEB-021):** runtime **delivered** — shared `SessionWarmer` pre-opens
  the first STT session at connect (no leak, `VOICE_STT_PREWARM`) + non-blocking
  `backend.warm_up()` trigger from `AnswerProcessor` (`POST /warm-up`, TASK-BE-017,
  `VOICE_BACKEND_WARMUP`); telemetry `voice.backend.warmup` (success/miss). Pending the
  live turn-1 cold-vs-warm sample.
