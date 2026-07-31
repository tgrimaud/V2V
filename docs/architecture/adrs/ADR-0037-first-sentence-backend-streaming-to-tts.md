# ADR-0037 — First-sentence backend answer streaming to TTS

- **Status:** Accepted for implementation (2026-07-30) — lever 1 built + unit/behave
  covered behind a default-off flag (TASK-WEB-020). **Warm live before/after validated
  (2026-07-30):** `VOICE_BACKEND_STREAM=1` delivered **−658 ms median** on
  `backend_first_token` and **−866 ms median mouth-to-ear** (2696.9 → 1830.6 ms p50; p95
  4848.7 → 2526.1 ms), DEC-002 preserved (5/5 grounded), filler coherence kept
  (4 → 1), barge-in intact — see
  [`streaming-voice-qa-report.md`](../../qa/streaming-voice-qa-report.md) "Live Lever-1
  Pass". **GO to enable the flag on the pilot channel** (strict improvement, no
  regression); **code default stays OFF** pending a larger warm+cold sample.
  **ADR-0029 gate (≤ 1500 ms p95) not yet met** — lever 1 is the biggest single mover but
  needs the STT finalize-tail work + lever-2 full-converse warm-up to attempt closure.
  Lever 2 delivered (TASK-WEB-021). Originally Proposed (2026-07-29).
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

## Lever 1 delivered (2026-07-30, TASK-WEB-020)

Implemented on the Flow A synchronous-per-turn path, behind the default-off env flag
`VOICE_BACKEND_STREAM` (opt-in `1/true/yes/on`); the blocking `POST /converse` path
stays the default and fallback. Capability-gated: the streaming path is taken only when
the backend actually exposes `answer_stream`, so a stub/fake without it transparently
stays blocking.

- **Backend SSE contract confirmed = point 2(a), stronger.** `ConverseStreamSession`
  emits `chunk` (one sentence), a terminal `done` (`{text, confidence?, grounded}`) and
  a sanitized `error` (ErrorResponse). `GuardedSentenceEmitter` runs grounding **then
  the output guardrail on each sentence before it is emitted**, and emits the safe
  hand-off as a **terminal `chunk`** on a block. So DEC-002 is enforced **per sentence
  on the stream** — no ungrounded amount can be voiced — which satisfies the ADR's
  non-negotiable safety contract (point 2) without any new backend work.

- **Confidence policy decision (Architecture + Product, the ADR's open lever-1
  question): option A.** Because the backend already grounds + guardrail-vets every
  emitted sentence, the terminal `done` confidence is treated as **advisory** on the
  streamed path: a grounded but low-confidence answer is **logged**
  (`voice.backend.stream.low_confidence`) and used for post-turn escalation, **not**
  un-said (it was already spoken). A backend `error`, an empty stream, or a raising
  adapter degrades to the same safe fallback the blocking path speaks; a non-grounded
  `done` (`grounded=false`) maps the turn to `DEGRADED` while still voicing the
  backend's own safe hand-off chunk. This keeps the full latency win with the DEC-002
  amount-safety gate intact, and is why the flag ships **off** until a live sample
  confirms the win and re-verifies guardrail behaviour.

- **Seam + safety of the consumer.** New neutral contract in
  `conversation_backend/streaming.py` (`AnswerStreamEvent`, `parse_sse_events`,
  `StreamControl`, `StreamingBackendAnswerPort`); `HttpBackendAdapter.answer_stream`
  consumes the SSE lazily (stdlib urllib, no new dependency), derives the
  `converse-stream` sibling of the configured converse URL, mirrors the blocking
  failure policy (never raises out, never leaks the key — a connect/mid-stream fault
  becomes one sanitized `error` event). `voice_pipeline/streaming_answer.py`
  (`StreamedAnswerRunner`) bridges the blocking generator to the loop with
  `await asyncio.to_thread(next, it, SENTINEL)` per event and pushes one `TextFrame`
  per vetted sentence; the streaming TTS synthesizes each incrementally (TASK-WEB-004,
  unchanged). The spoken filler (TASK-WEB-019) is settled on the first pushed sentence
  so it cannot double-speak.

- **Barge-in.** An interruption cancels the runner; it catches `asyncio.CancelledError`,
  calls `StreamControl.abort()` (sets the stop flag **and closes the socket** so a read
  blocked mid-line unblocks), emits `voice.backend.stream.interrupted`, and re-raises —
  no sentence is pushed after cancellation and the connection is closed (best-effort).

- **Telemetry (US-036).** `backend.first_token` now stamps the **first sentence** (the
  lever-1 win) and `backend.request` the total on the streamed path — same span names so
  the existing per-slice distributions carry over; plus `voice.backend.streamed`
  (sentence count, outcome, grounded, confidence) and the advisory/interrupted events
  above.

- **Coverage.** `tests/test_streaming_answer.py` (parser, runner ordering, blocked
  hand-off, error/empty/raising degrade, option-A advisory, barge-in no-post-cancel-
  speech + socket close, flag on/off + capability fallback), `tests/test_http_backend.py`
  (URL derivation, chunk/done parse, sanitized error, empty transcript, abort closes),
  and `features/first_sentence_streaming.feature`. Full suite green (unittest 462,
  behave 13·36·169).

- **Still pending (the gate to switch the flag on):** a warm+cold **live** before/after
  sample on the real backend, per-slice + composite p50/p95/p99 vs the TASK-WEB-014
  baseline, ADR-0029 gate re-evaluated, and the QA report go/no-go.

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
Observability: `voice.backend.warmup` (success/miss) + `voice.stt.prewarm` (hit/fallback/
cold) events with count metrics, all carrying correlation id + provider.

Adversarial-review fixes (2026-07-29): the STT pre-warm is **off by default (opt-in via
`VOICE_STT_PREWARM=1`)** because `acquire()` only recovers from an open *failure*, not from
a spare that the ASR server drops while idle — a stale spare would degrade turn 1, so it
stays opt-in until a live sample confirms Gradium's idle behaviour. The connect-time
backend warm-up (side-effect-free, the larger win) stays on by default (`VOICE_BACKEND_WARMUP`).
`SessionWarmer.aclose()` no longer swallows an external `CancelledError` (only the spare's
own expected cancellation); `HttpBackendAdapter` derives the `/warm-up` URL robustly
(trailing slash / query stripped).

**Live turn-1 cold-vs-warm sample captured (2026-07-30, real backend + `/warm-up` via a
TASK-BE-017 worktree; see the QA report "Live Lever-2 Pass" section).** Mechanism confirmed:
`voice.backend.warmup = success` at connect on both treatment sessions; `voice.stt.prewarm
= hit` on the first STT open of each session → **Gradium preserves the pre-opened idle
socket**, spare reused on turn 1, **no fallback/leak** (opt-in `VOICE_STT_PREWARM=1`
validated live). Turn-1 `stt.request` (379 ms) and `backend.first_token` (4.4 ms/char) are
flat with warm turns. A **deterministic backend micro-benchmark** (fixed transcript, cold
vs warm) isolates the mechanism from generation-length noise: without warm-up the turn-1
backend cold penalty is **+448 ms typical and can spike to multiple seconds** (a cold first
Mistral call + JVM JIT produced an 8.5 s call-1); with warm-up it is **bounded to
~1.2–1.3 s** (residual ~300–390 ms). `/warm-up` costs ~0.7–1.4 s off-path.
**Residual finding:** `/warm-up` warms embedding + LLM but **not** the full converse
critical path (RAG/pgvector, guardrail, sentence emitter), leaving ~300 ms of turn-1 JIT —
**follow-up:** have `/warm-up` run a full dummy converse so those paths warm off-path too.
Lever 2 is a **turn-1-only** win and **does not move the ADR-0029 gate alone** — lever 1
remains decisive. STT pre-warm stays **opt-in** (positive but small live sample, n=2),
ready to flip default-on after a larger sample.

## Status of TASK-WEB-015 at this ADR

- **Lever 3 (end-of-turn hold tuning):** implemented (env-tunable
  `VOICE_END_OF_TURN_SILENCE_MS`, clamped to a 250 ms safe floor, default 500 ms) —
  offline, deterministic, testable now.
- **Lever 1 (this ADR):** designed + gated on the DEC-002 SSE contract and the
  TASK-WEB-014 live baseline (default-off feature flag).
- **Lever 2 (TASK-WEB-021):** runtime **delivered** — shared `SessionWarmer` pre-opens
  the first STT session at connect (no leak; **opt-in** `VOICE_STT_PREWARM=1`, off by
  default pending live idle-socket validation) + non-blocking `backend.warm_up()` trigger
  from `AnswerProcessor` (`POST /warm-up`, TASK-BE-017, `VOICE_BACKEND_WARMUP` on by
  default); telemetry `voice.backend.warmup` (success/miss) + `voice.stt.prewarm`
  (hit/fallback/cold). **Live turn-1 sample captured 2026-07-30** — mechanism confirmed
  (warmup=success, prewarm=hit, Gradium keeps the idle socket, no fallback/leak); backend
  cold penalty bounded from +448 ms (up to multi-second) to ~300–390 ms residual;
  turn-1-only win, ADR-0029 gate still needs lever 1. Follow-up: warm the full converse
  path (RAG/guardrail/sentence-emitter), not just embedding + LLM.
- **Backend support (TASK-BE-017, validated + merged 2026-07-31):** the backend side of
  both levers is delivered. `POST /api/conversation/warm-up` exercises the embedding
  (retrieval) + the LLM once, touches no conversation memory, discards the output, is
  repeatable and non-blocking (a warm-up miss returns 200 with per-model flags false), and
  records `warmup_embedding` / `warmup_llm` latency slices — this is the endpoint the
  TASK-WEB-021 connect trigger consumes. For lever 1, the investigation confirmed
  `converse-stream` (SSE, ADR-0013) **already** emits guardrail-vetted sentences one at a
  time via `GuardedSentenceEmitter` (DEC-002 enforced backend-side, no contract change
  needed), locked by a service-level incremental-delivery contract test in
  `StreamingConversationServiceTest` (first vetted sentence reaches the consumer before the
  full answer; blocked sentence → safe hand-off).
