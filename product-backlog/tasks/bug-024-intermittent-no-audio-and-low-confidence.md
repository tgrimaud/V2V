# BUG-024 — Intermittent no-audio turns + intermittent LOW_CONFIDENCE fallback on covered EN billing/roaming questions

## Header

- **Bug ID:** BUG-024
- **Title:** Some voice turns return no spoken audio, and covered EN billing/roaming questions intermittently degrade to the LOW_CONFIDENCE hand-off
- **Status:** In progress — symptom (b) root-caused + fixed on the streaming path (pending QA retest + user validation); symptom (a) dead-air deferred (needs voice-tier/TTS repro). **Note (2026-09-23):** ticket landed to `feat/restart-from-scratch` for tracking; the symptom-(b) **code fix is not yet in mainline** — it lives on the WIP branch `fix/BUG-024-nonanswer-courtesy-handoff` (to be rebased on mainline before merge).
- **Severity:** Medium
- **Priority:** P2
- **Detected by:** Developer (latency wave, TASK-BE-033 / ADR-0029 measurement session)
- **Detected date:** 2026-09-21
- **Related user story:** US-036 (per-slice latency) / US-041 (voice turn lifecycle)
- **Related epic:** EPIC-006 (voice latency) / EPIC-005 (answer engine) / EPIC-012 (pilot)
- **Branch:** `fix/BUG-024-nonanswer-courtesy-handoff` (symptom b)
- **Owner:** Cross-functional (voice runtime developer + backend developer)

## Problem Statement

During the 2026-09-21 pilot latency waves two intermittent reliability symptoms
appeared on the same questions that succeed on other iterations:

1. **No-audio turns** — on the Genesys/streaming path, **2 of 12** turns produced
   **0 bytes of bot audio** (dead air): the caller got no spoken answer and no audible
   hand-off, even though the WebSocket handshake and control frames opened/closed
   normally.
2. **Intermittent LOW_CONFIDENCE degrade** — on the batch path, **4 of 12** turns for
   the *same* covered questions ("my bill increased", "roaming charges") returned the
   short (~120-char) LOW_CONFIDENCE safe fallback instead of a grounded answer, while
   other iterations of the identical question answered normally.

Both are non-deterministic on inputs that are covered by the KB, which points to
retrieval/confidence variance at the margin rather than a hard functional gap.

## Environment

- **Environment:** pilot (backend 0.9.2, post BUG-022/BUG-023 KB re-sync)
- **Channel:** Genesys AudioHook / streaming (symptom 1) and batch `/api/voice/turn` (symptom 2)
- **Provider configuration:** STT/TTS Gradium (streaming), LLM `mistral-small-latest` (`LLM_PROVIDER=mistral-api` pinned on pilot), embedding Ollama `nomic-embed-text`, top-k=5
- **Build or commit:** pilot voice `v0.8.x` bridge + backend 0.9.2 (`feat/restart-from-scratch`)
- **Correlation ID:** wave `gwave-1789995191-01..12` (streaming) and `wave-en-*` (batch); note the
  server mints its own per-turn `correlation_id`, distinct from the client `conversation_id`, so
  the client id alone does not select the server spans

## Reproduction Steps

1. Given the pilot backend 0.9.2 with the re-synced KB, warm.
2. When the same EN billing/roaming clips ("my bill increased", "roaming charges") are
   sent repeatedly — via `genesys_local_client.py` (streaming) and `/api/voice/turn` (batch).
3. Then a minority of iterations either return 0 audio bytes (streaming) or the
   short LOW_CONFIDENCE fallback (batch), while the majority answer normally.

## Expected Result

- **Every** turn yields spoken audio — a grounded answer or an *audible* safe hand-off;
  a turn must never end in dead air.
- A question that is answerable from the KB should not intermittently fall to the
  LOW_CONFIDENCE hand-off; the grounded/degraded outcome should be stable for a stable input.

## Actual Result

- 2/12 streaming turns: 0 audio bytes, no spoken answer, no audible hand-off (dead air).
- 4/12 batch turns: LOW_CONFIDENCE ~120-char fallback on covered questions that
  succeeded on other iterations.

## Evidence

- Latency waves (2026-09-21): streaming `gwave-1789995191-*` (12 turns, 2 with 0 egress bytes);
  batch `wave-en-*` (12 turns, 4 `outcome=degraded degraded_reason=low_confidence`).
- Streaming per-slice latency report (same session): `stt` p50 397/p95 416 ms,
  `backend_first_token` p50 849/p95 1732 ms, `tts_first_audio` p50 363/p95 406 ms,
  composite mouth-to-ear p50 ~1979/p95 ~2819 ms (see TASK-BE-033 evidence note).
- Backend logs for the two no-audio correlation ids were **not recoverable** at
  investigation time (json-file rotation, same retention gap noted on BUG-018) — the
  first fix step is to re-run the wave with the server `correlation_id` captured per turn.

## Impact

- **customer:** dead-air turns feel like the bot froze (perceived reliability failure,
  same UX class as BUG-018 hang-until-refresh); a generic hand-off on a covered topic
  wastes the self-serve deflection.
- **advisor / operational:** avoidable escalations when the KB actually covers the answer.
- **latency/SLO:** independent of latency, but measured in the same ADR-0029 session; a
  no-audio turn is effectively an infinite mouth-to-ear for that turn.
- **pilot-readiness:** reliability blocker to characterise before any Genesys-path SLO claim.

## Acceptance Criteria For Fix

- [ ] No-audio turns eliminated: every turn produces spoken audio (grounded answer or an
      audible hand-off); a dead-air turn is impossible or emits a terminal error signal
      the caller/UI can act on (aligns with BUG-018 / TASK-WEB-045/046).
- [ ] The LOW_CONFIDENCE rate on covered EN billing/roaming questions is characterised
      (grounding confidence distribution per question) and either reduced (retrieval /
      threshold / re-sync fix) or justified with evidence.
- [ ] Root cause of the 0-byte turns identified (empty answer vs blocked emitter with no
      voiced fallback vs TTS-not-invoked vs stream error) with a regression test.
- [ ] OpenTelemetry: per-turn server `correlation_id` is captured end-to-end so a no-audio
      turn can be traced (retrieval evidence_count/confidence, guardrail verdict, TTS bytes).
- [ ] Adversarial code review ≥ 90% satisfied.
- [ ] QA retest passes (wave with the same questions shows stable grounded outcomes + no dead air).

## Investigation Leads

- **Confidence at the margin:** `GuardedSentenceEmitter` emits the LOW_CONFIDENCE fallback
  when `groundedConfidence` is below the band; borderline retrieval for these two EN queries
  likely oscillates across the threshold between iterations (retrieval variance, EN recall,
  or a chunk that just misses top-k=5). Capture the per-turn `confidence` + `evidence_count`.
- **No-audio (0 bytes):** determine whether the turn (a) produced an empty LLM answer that
  the emitter blocked with **no** voiced fallback, (b) errored on the stream/TTS after the
  answer, or (c) never invoked TTS. Cross-check with BUG-018 (no guaranteed terminal signal)
  and BUG-017 (barge-in self-interrupt could cut the output track to 0 bytes).
- **Relation to STT:** confirm the no-audio turns are not STT no-transcript cases (empty final
  → empty question → guardrail hand-off with no voiced text).

## Developer Notes

### Investigation 2026-09-22 (symptom b — intermittent LOW_CONFIDENCE)

Reproduced deterministically on the pilot backend via text-in `POST /converse-stream` (real
retrieval + guardrails, no STT/TTS noise). Provider is now **OpenAI `gpt-5`** (`LLM_PROVIDER=openai`,
`reasoning_effort=minimal`), **not** the mistral pin the ticket assumed.

- **Retrieval + confidence are DETERMINISTIC.** Repeating each covered question ×15, the returned
  confidence (= best evidence similarity, `RetrievalConfidenceGuardrail`) was identical every time
  (`conf_distinct_count=1` per question, e.g. bill-increase 0.695552, roaming 0.810075, voicemail
  0.745642) and **all well above the 0.5 floor**. So the "intermittency" is **not** retrieval
  variance and **not** the retrieval-confidence guardrail — the ticket's "oscillation on identical
  input" premise is corrected.
- **The flip happens at the OUTPUT stage.** Despite stable, above-floor retrieval confidence,
  `grounded` still flipped to false on ~13% of turns (grounded_rate 0.87–0.90 on the marginal
  questions). Backend logs showed **all** these fallbacks as `[GUARDRAIL] verdict=low_confidence`
  (none `ungrounded`) → the `OutputGuardrail.isNonAnswer` path: the LLM's own answer intermittently
  contains a **hand-off marker** ("transfer you to an advisor") or comes back empty, and the guard
  treated the **whole answer** as a refusal.
- **Amplifier:** gpt-5 is forced to `temperature=1.0` (a lower value is rejected 400; see `LlmConfig`),
  i.e. maximally stochastic wording, whereas Mistral/Ollama run at 0.2 *precisely* "to reduce
  non-deterministic refusals". At 1.0 gpt-5 more often appends a courtesy transfer to an otherwise
  grounded answer, tripping the substring marker match.

### Fix (symptom b)

`GuardedSentenceEmitter` (streaming path, ADR-0013): a `LOW_CONFIDENCE`/hand-off sentence that
arrives **after** grounded content was already voiced is a **trailing courtesy transfer, not a
refusal** — keep the grounded answer and drop the hand-off sentence (`truncatedAfterGrounded`),
instead of discarding the whole turn to a fallback. A genuine refusal is the first/only sentence
(nothing voiced yet) and still hands off. **`UNGROUNDED` (a DEC-002 ungrounded amount) ALWAYS
blocks**, regardless of what was voiced, so no fabricated amount can leak.

- **Files:** `backend/.../domain/service/GuardedSentenceEmitter.java` (+ `stopped()` guard,
  `truncatedAfterGrounded`); tests in `GuardedSentenceEmitterTest`
  (`trailing_handoff_after_grounded_stays_grounded`, `ungrounded_amount_after_grounded_still_blocks`).
- **OpenTelemetry:** no new instrumentation required — `[GUARDRAIL] verdict=…` is already emitted;
  the fix reduces the count of *false* `low_confidence` verdicts (observable as a higher grounded
  rate on the same wave), and the DEC-002 `ungrounded` path is unchanged.
- **Scope:** streaming path only (where the symptom is measured; the batch `/api/voice/turn` also
  streams by default per BUG-015). The synchronous `/answer` whole-answer `isNonAnswer` is unchanged
  (a whole-answer variant would need a fuzzier "predominantly a refusal" heuristic; deferred).
- **Residual risk:** a genuine refusal phrased as a *trailing* sentence after some grounded content
  is kept as grounded (the grounded content is voiced, the refusal dropped) — acceptable, since a
  grounded answer WAS produced. `mvn -o test` green (591/0).

### Symptom (a) dead-air — root cause found live (2026-09-22)

Initially not reproducible on the text path (`zero_chunk_turns=0` across the first 105 turns). It
then reproduced en masse during a heavier probe when the LLM provider started returning
**`429 Too Many Requests`** (Azure Foundry `Ai4cc-POC-SWD…`, gpt-5): on an upstream LLM stream
failure `ConverseStreamSession` throws `UpstreamUnavailableException` and emits an SSE **`error`
event (`ERR_UPSTREAM`) with NO voiced chunk** (`[CONVERSE-STREAM] code=ERR_UPSTREAM
type=UpstreamUnavailableException`, `zero_chunk_turns` spiking to ~16–20/20).

- **Root cause of the 0-byte turns = the stream-error branch has no *voiced* fallback.** On the
  Genesys/AudioHook path an `error` event yields no TTS → **0 audio bytes = dead air**, exactly the
  original 2/12 symptom (which happened while the provider was mistral; same class of failure).
- **Proposed fix (not yet implemented — user chose to defer (a)):** on an LLM stream error, emit an
  **audible safe hand-off chunk** ("I'm having trouble right now, I'll transfer you to an advisor")
  before/instead of the silent `error` event, so a provider hiccup can never end in dead air
  (aligns with BUG-018 "guaranteed terminal signal" + TASK-WEB-045/046). Add a regression test that
  a thrown upstream error still produces ≥1 voiced chunk.
- **Operational note:** the shared **Azure POC endpoint has a low request quota**; back-to-back
  measurement waves (280+ LLM turns) tripped `429`. Throttle future probing or measure off-peak.

### A/B (symptom b fix) — attempted, CONFOUNDED by the 429 storm

The pilot QA-retest A/B (t04 baseline 0.9.2 vs t03 fix `sha-0d01cf7`, 140 turns each) ran **into the
same 429 storm** (both nodes hit the one throttled endpoint in parallel): baseline OVERALL grounded
0.164 vs fix 0.850, but that gap reflects **which probe got throttled**, not the fix — invalid as
evidence. The fix stands on its unit tests (591/0); a clean grounded-rate A/B must be re-run when the
provider is not rate-limited (or with gentle, serialized probing).

## QA Retest

- **Retested by:**
- **Retest date:**
- **Scenarios rerun:**
- **Result:**
- **Retest evidence:**

## Closure

- **Closed by:**
- **Closed date:**
- **Closure reason:**
