# ADR-0035 — Conversational end-of-call on a customer farewell

- **Status:** Accepted (2026-07-27)
- **Deciders:** Product + Architecture (user-validated design decisions)
- **Related:** US-041, TASK-WEB-010, ADR-0002 (streaming voice path), ADR-0033
  (WebRTC single live transport), TASK-WEB-008 (graceful drain / barge-in)
- **Supersedes / touches:** none

## Context

Today a streaming voice call only ends when the browser closes the WebRTC session
(`closed`/`disconnected` → `WebRtcSignalingService._drain_and_discard`). There is no
*conversational* way to end a call: when the customer says "merci, au revoir" the bot
keeps the channel open and answers the farewell as if it were a question. US-041 asks
the bot to end the call cleanly when the customer signals they are done.

Constraints that shape the decision:

- **No LLM intent classifier in V1** (DEC-041-b): detection must be deterministic,
  cheap and testable, consistent with the existing guardrail / barge-in style.
- **False positives are costly**: cutting a call because a closing word appeared inside
  a longer request ("avant de dire au revoir, une question sur ma facture") is worse
  than missing a farewell. This mirrors the `contains()` lesson from the Java
  `InputGuardrail` and the barge-in echo work — naive substring matching is fragile.
- **Reuse, don't reinvent, teardown**: TASK-WEB-008 already added a graceful
  `drain()` (`stop_when_done` → `EndFrame`) that lets in-flight audio play before the
  pipeline stops. The farewell path must reuse it, not build a second teardown.
- **Observability is mandatory**: pilot review needs to tell a bot-ended call
  (`customer_farewell`) apart from a manual hangup (`client_stop`) or an error/drop.

## Decision

1. **Hybrid, deterministic detection (no LLM).** A pure `ClosingIntentDetector`
   (`web_voice/closing_intent.py`) works on the **final** transcript only. It:
   - normalises text to accent-folded, lowercased word tokens (stdlib `unicodedata`);
   - matches a **config-tunable FR phrase list** as a *contiguous token subsequence*
     (word-boundary, never `contains()`);
   - **rejects negation**: a negation token (`pas`, `jamais`, …) immediately before the
     matched phrase (`non, pas au revoir`) is not a closing;
   - **rejects embedded requests**: any leftover token that is not an allowed politeness
     filler means the closing word sits inside a longer request → not a standalone
     closing.
   The same normaliser powers `is_done_confirmation()` for the confirmation turn.

2. **Confirmation turn (DEC-041-a).** On a detected closing the bot does **not** answer;
   it speaks "Souhaitez-vous autre chose ?" (a plain `TextFrame`, synthesised by the
   existing TTS stage) and enters an `AWAITING_CONFIRMATION` state. It ends the call only
   when the customer confirms they are done (`non`, `c'est tout`, `rien d'autre`, …) **or
   stays silent**; any other utterance cancels the farewell and is answered normally.

3. **Bounded confirmation-scoped silence timer.** Silence-as-confirmation is implemented
   as an `asyncio` timer that is armed **only** in `AWAITING_CONFIRMATION`
   (`VOICE_FAREWELL_CONFIRM_TIMEOUT_S`, default 6 s). This is deliberately **not** a
   general mid-call silence-timeout end-of-call (OQ-041-c, explicitly out of scope): the
   timer exists only while waiting for the confirmation answer and is cancelled as soon
   as any frame arrives or the pipeline tears down.

4. **Pipeline placement.** The farewell logic is a `FrameProcessor`
   (`CallEndFarewellProcessor`) inserted **between STT and the answer step** via a new
   `pre_answer` seam on `StreamingVoiceSession`. It intercepts `TranscriptionFrame`s
   (suppressing the answer on a farewell), speaks by pushing plain `TextFrame`s, and
   forwards everything else untouched.

5. **Teardown reuses TASK-WEB-008.** To end the call, the processor calls an injected
   `end_call(signal)` callback. The signaling service records the end-of-call reason and
   then reuses the existing `drain()` path: the closing message is spoken, the queued
   `EndFrame` lets it play out, and the connection is disconnected — routing through the
   same `_drain_and_discard` teardown/telemetry-dump as a browser hangup.

6. **End-of-call reason telemetry.** A `voice.call_end` event + span records the reason
   under the call correlation id: `customer_farewell` (with `signal=confirmation|silence`)
   vs `client_stop` (manual/drop) vs `error`. This is new: `client_stop` previously
   existed only as an end-of-*turn* signal, not an end-of-*call* reason.

7. **FR only in V1 (BR-041-4).** The phrase sets are French; they are env-tunable
   (`VOICE_FAREWELL_PHRASES`, `VOICE_FAREWELL_DONE_PHRASES`) exactly like the barge-in
   thresholds, so a deployment can adjust them without a code change.

## Consequences

**Positive**

- Natural call endings without a browser hangup; the channel is released.
- Deterministic, unit-testable detection with an explicit false-positive guard; no LLM
  latency or cost on the closing path.
- One teardown path (TASK-WEB-008) for both manual and conversational endings.
- Pilot review can attribute every call ending to a reason.

**Negative / risks**

- Phrase-list detection cannot capture every phrasing; the env-tunable list is the lever,
  and a missed farewell simply leaves the pre-existing manual-hangup behaviour intact.
- The confirmation timer adds a small amount of async state to the pipeline; it is scoped
  to the confirmation window and cancelled on any frame/teardown to avoid a stray end.
- A bot-initiated end depends on the `EndFrame` draining through a *live* transport; if
  the closing audio cannot drain within a timeout, teardown proceeds anyway (the closing
  may be cut) rather than hanging the session.

## Alternatives considered

- **LLM intent classification** — rejected for V1 (DEC-041-b): latency, cost and
  non-determinism on a safety-adjacent "hang up" action; revisit if phrase lists prove
  insufficient.
- **No confirmation step (end immediately on a closing word)** — rejected (DEC-041-a):
  too aggressive given false-positive risk; the confirmation turn is the safety net.
- **A general silence-timeout end-of-call** — deferred (OQ-041-c): a separate story;
  here silence is only interpreted inside the confirmation window.
- **Pushing an `EndFrame` downstream from the processor** instead of `drain()` — rejected:
  duplicates teardown and bypasses the TASK-WEB-008 path and its telemetry dump.
