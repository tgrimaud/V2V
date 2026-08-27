# TASK-STT-014 — STT post-end-of-turn finalize-tail (partial-quiet early accept) QA & review

**Ticket:** TASK-STT-014 (Reduce the post-end-of-turn STT finalize tail on the live real-backend path)
**Parent:** EPIC-010
**Related:** ADR-0029 (pilot latency gate), ADR-0018 (voice latency targets), TASK-STT-013 (finalize-on-`flushed`), TASK-WEB-035 (bounded finalize budget), US-036 (per-slice timing)
**Branch:** `task/TASK-STT-014-stt-finalize-tail` (off `feat/sprint-12-external-voice-websocket`)
**Date:** 2026-08-27
**Status:** Implementation + unit/behave tests + adversarial review complete. **Ships default-OFF.** Live STT-tail A/B measured 2026-08-27 (§7): at `VOICE_STT_PARTIAL_QUIET_MS=300` the reconcile gauge shows **trailing-word loss on ~100 % of engagements** (`extra_words ≈1`, `reconciled_match=0`) for only ~99 ms median saved — the correctness gate **fails at 300 ms**, so the lever stays **OFF**. Formal WER pass still outstanding, but the reconcile gauge is already decisive.

## 1. Lever chosen and rationale

**Lever: partial-quiet early finalization** — on the streaming path, once the partial stream
has been *quiet* for a configurable window (`VOICE_STT_PARTIAL_QUIET_MS`, no new partial), accept
the settled partials as the effective final and let the pipeline proceed, **without** blocking on
the provider's terminal ack (`flushed` ~350 ms / `end_of_stream` ~780 ms — STT-013 spike). The
true terminal is then **reconciled asynchronously**, off the critical path, so a would-be dropped
trailing word is *observable* (`voice.stt.finalize_reconcile`, `extra_words > 0`), never silent.

### Why this shape (and honest caveat)

The TASK-STT-013 spike already established two hard facts this ticket must respect:

1. The finalize tail after STT-013 is the deterministic **`flushed`** round-trip (~350 ms), and the
   last delta partial lands at ~60–204 ms after our end-of-turn flush.
2. **Commit-on-last-partial was rejected in STT-013** because Gradium's `delay_in_frames` (~800 ms
   lookahead) means the trailing word can still be buffered at flush and only emitted during the
   tail. STT-013 also noted a naive last-text debounce "makes it no better than the deterministic
   ~350 ms `flushed` ack, for added accuracy risk."

Therefore TASK-STT-014 does **not** claim a guaranteed win. It delivers the *mechanism* plus the
*safety instrumentation* so the live gate can **decide with data** whether a partial-quiet window
beats `flushed` on the real backend and at what word-loss cost — instead of a code-baked guess.
This is why it ships **default-OFF** (`VOICE_STT_PARTIAL_QUIET_MS` unset ⇒ 0.0 ⇒ the unchanged
WEB-035 path), mirroring `VOICE_STT_PREWARM` staying opt-in pending live validation, and consistent
with ADR-0029 point 5 (the residual STT headroom is small and high-risk).

### Options considered

| Option | Post-EOT tail | Trailing-word risk | Verdict |
|---|---:|---|---|
| Wait terminal `flushed` (STT-013, current default) | ~350 ms | none (lossless by construction) | Baseline — kept as default |
| WEB-035 budget cap (already merged) | ≤ budget on a *stalled* terminal | none (same joined partials) | Kept, unchanged |
| **Partial-quiet early accept + async reconcile (this ticket)** | quiet window (tunable, e.g. ~250–300 ms) | possible, **measured** by reconcile | **Chosen, default-OFF, live-gated** |
| Commit-on-last-partial at flush | ~100 ms | drops trailing word every run | Rejected in STT-013 |
| `delay_in_frames` tuning | smaller | accuracy cost | Deferred (provider-config lever) |

## 2. Implementation

| File | Change |
|---|---|
| `voice-agent/stt_validation/streaming.py` | Added `wait_progress(timeout)` + a `_progress` `asyncio.Event` on `GradiumStreamingSession`, set on every new partial and on both terminal paths (`_finalize_from_parts`, `_fail`). Off-protocol optional capability (accessed via `getattr`), so `StreamingSttSession` conformance and the batch provider are untouched. |
| `voice-agent/web_voice/streaming_stt_processor.py` | `_await_final` dispatches to `_await_terminal` (unchanged WEB-035 path) or the new `_await_with_quiet`. `_await_with_quiet` waits in quiet slices for the next partial or the terminal; on a quiet slice with partials in, accepts the snapshot early (`_finalize_early`). Early-accepted turns spawn `_reconcile` (async, off critical path) which compares against the true terminal, emits the reconcile signal, and owns the session `aclose`. `_drain_reconcile_tasks` cancels+awaits in-flight reconciles on `EndFrame`/`CancelFrame` (no socket leak). New telemetry: `voice.stt.finalize_early` + `voice.stt.finalize_reconcile`. |
| `voice-agent/web_voice/session_factory.py` | `_partial_quiet_config()` parses `VOICE_STT_PARTIAL_QUIET_MS` (fail-safe: unset/invalid/≤0 ⇒ off) and unpacks it into the processor kwargs. |
| `voice-agent/tests/test_streaming_stt_processor.py` | `QuietFakeSession` + 5 new GIVEN/WHEN/THEN tests (real `TelemetryRecorder`). |
| `voice-agent/features/streaming_stt.feature` + steps | 1 new behave scenario for the early-accept journey with the reconcile guarantee. |

### Safety invariants preserved (ticket scope)

- **Transcript = concatenation of real partials.** The accepted snapshot is exactly the
  `" ".join(parts)` the terminal path builds (`partial_snapshot()`); no invention. `_nonempty_snapshot`
  refuses to finalize an *empty* snapshot, so a genuine provider stall still surfaces on the failure
  path (degraded fallback), never a fabricated empty turn.
- **WEB-035 semantics kept.** The finalize budget cap and the hard failure ceiling both still apply
  inside `_await_with_quiet`; the quiet lever only shortens the wait on a *healthy* turn whose
  partials are already in. Budget fallback still emits `voice.stt.finalize_fallback`.
- **Terminal still wins if it lands first** (unchanged STT-013 behavior); an error terminal still
  raises `StreamingSttError` ⇒ degraded fallback.
- **API key / transcript never logged.** Reconcile telemetry carries word *counts* only, no text (PII).

### p95 pollution guard (WEB-035 pitfall)

The early-accept path is **success-only** and emits the `stt.request` span with the *real, shorter*
early tail — it legitimately improves p95, it does not inject a stalled-terminal duration. The async
reconcile emits its **own** event/metric and **no** `stt.request` span, so a slow/absent terminal
after a good early accept cannot pollute the `stt` slice distribution. A regression test asserts the
span outcome is `success` on the early-accept turn.

## 3. Telemetry (sanitized, correlation-id + per-turn baggage)

| Signal | When | Key attributes |
|---|---|---|
| `voice.stt.finalize_early` (event) + `voice.stt.finalize_early.count` (metric) | quiet window accepted the settled partials before the terminal | `partial_quiet_ms`, `accepted_word_count`, `time_to_final_ms` |
| `voice.stt.finalize_reconcile` (event) + `voice.stt.finalize_reconcile.extra_words` (metric) | async reconcile of an early-accepted turn vs the true terminal | `reconciled_match`, `terminal_available`, `accepted_word_count`, `terminal_word_count`, `extra_words`, `early_time_to_final_ms`, `time_saved_ms` |

`extra_words > 0` (with `reconciled_match=false`) is the **dropped-trailing-word gauge** the live gate
reads to size `VOICE_STT_PARTIAL_QUIET_MS`. `time_saved_ms` quantifies the tail avoided by not waiting
for the terminal.

## 4. Test evidence (all green, via `voice-agent/.venv`)

- `./.venv/bin/python -m unittest discover tests` → **573 tests OK** (5 new for this ticket).
- `./.venv/bin/behave` → **17 features / 47 scenarios / 214 steps passed** (1 new scenario).

New unit tests (GIVEN/WHEN/THEN):
- `test_partial_quiet_finalizes_early_before_terminal` — early accept on a stalled terminal; lossless
  join; `finalize_early` event/metric; `stt.request` span stays **success** (p95 guard).
- `test_partial_quiet_reconcile_matches_true_terminal` — reconcile match, `extra_words=0`, session closed by reconcile.
- `test_partial_quiet_reconcile_flags_dropped_trailing_word` — terminal carries an extra trailing word ⇒ `reconciled_match=false`, `extra_words=1` gauge; customer still got the early answer.
- `test_partial_quiet_disabled_by_default_uses_terminal` — default-OFF ⇒ WEB-035 terminal path, no early/reconcile events.
- `test_partial_quiet_terminal_wins_when_ack_is_fast` — a fast ack wins, no early accept/reconcile.

New behave scenario: *"Partial-quiet finalizes early without waiting the stalled terminal ack"* —
observable journey: final produced, `finalize_early` recorded, terminal reconciled with no dropped word.

## 5. Adversarial code review — score 92/100 (PASS)

Applied `.cursor/skills/adversarial-code-review/SKILL.md`.

**Strengths:** default-safe/opt-in; WEB-035 + failure semantics preserved; success-only span
(no p95 pollution); no-dropped-word guarantee is *observable* via reconcile (not just asserted);
PII-safe telemetry; reconcile lifecycle (spawn + drain on teardown, single `aclose`, best-effort
close) is leak-free; provider-agnostic (off-protocol `getattr` seam, batch provider untouched);
env parsing fails safe.

**Findings / residual risk (deductions):**
- **−5 (must be closed by QA, by design):** the live word-loss rate of a given quiet window is
  **unproven here** — this is inherent to the STT-013 caveat and is exactly why the feature ships
  OFF and instruments the reconcile gauge. Closed only by the live gate below.
- **−3 (accepted):** when partial-quiet is ON but **no** partial has arrived, `_await_with_quiet`
  polls in `quiet`-sized slices until the terminal lands or the ceiling; it wakes immediately on the
  terminal (progress event), so it is bounded and cheap, but it is a short poll rather than a single
  await. Acceptable for a default-OFF, small-window lever.
- **Note (no deduction):** the first `wait_progress` after finalize may return immediately on the
  leftover "set" from the last streamed partial; this is intentional — it forces a full quiet window
  to be measured from the finalize point (conservative, safer against word loss).

Score **92 ≥ 90 ⇒ PASS**. No functional blocker; the one material residual is the live WER/tail
measurement, tracked as the QA gate.

## 6. Remaining QA gate (live, cannot run in this environment) — DO NOT fabricate

A full live re-score needs real Gradium STT + the real backend and was **not** run here. To close
the ticket's acceptance criteria:

1. Deploy with the lever ON at a candidate window, e.g. `VOICE_STT_PARTIAL_QUIET_MS=300`.
   Source `GRADIUM_*`/`MISTRAL_*` from the repo-root `.env` (`set -a; . ../.env; set +a`).
2. Run the streaming WebRTC latency harness warm **and** cold (as in STT-013/WEB-035), capturing
   per-slice p50/p95/p99, and record the `stt` slice before/after.
3. Read the new gauges over the run: `voice.stt.finalize_early.count` (engage rate) and
   `voice.stt.finalize_reconcile.extra_words` (**word-loss rate — must be ~0**). If `extra_words`
   is non-zero at a meaningful rate, **increase** the window (toward the ~350 ms `flushed` cost) or
   keep the lever OFF — STT-013's conclusion stands until the live data contradicts it.
4. Run the formal **WER** pass on the fixture set with the lever ON; **WER must be unchanged**
   vs the `flushed` baseline (zero word loss).
5. Re-evaluate the mouth-to-ear composite against the **ADR-0029 gate (≤ 1500 ms)** combined with
   levers 1 (TASK-WEB-020) + 2 (TASK-WEB-021), and confirm **no regression in barge-in or the
   US-036 telemetry slices**.
6. Record the measured numbers here + in ADR-0029; only then flip the recommendation from
   "OFF pending validation" to a deployed default (if the data supports it).

No latency or WER numbers are asserted in this document because they were not measured live.

## 7. Live measurement (2026-08-27, local full stack, real providers) — lever OFF vs ON

Measured on the merged sprint-12 state, local full stack with **real** providers (Gradium
STT/TTS + Mistral chat + Ollama embeddings, pgvector `vector_store` = 10 163 rows), WebRTC
streaming path, headless `scripts/webrtc_live_client.py` driving 5 French billing questions
(DTX-safe low-amplitude noise tail), per-slice via `scripts/streaming_latency_report.py`.
Candidate window: **`VOICE_STT_PARTIAL_QUIET_MS=300`** (AFTER) vs unset (BEFORE, WEB-035
terminal path). Warm.

### `stt` finalize-tail slice

| Config | p50 | p95 | n |
|---|---:|---:|---:|
| BEFORE (STT-014 OFF, terminal `flushed`/budget) | 346 ms | 1200 ms | 12 |
| AFTER (STT-014 ON, quiet=300 ms) | 344 ms | 460 ms | 37 |

- **p50 unchanged** (346 → 344 ms): on a healthy turn the terminal `flushed` ack already
  lands ~350 ms, so the quiet window saves nothing at the median.
- **p95 drops** (1200 → 460 ms): the tail improvement is real — the 1200 ms BEFORE p95 is the
  WEB-035 budget cap hit on a stalled terminal, which the early accept avoids. But this tail
  win is **not free** — see the correctness gate below.

### CRITICAL correctness gate — trailing-word loss (FAILS at 300 ms)

The `voice.stt.finalize_reconcile` gauge over the AFTER run:

- **Early-accept engaged 15 times** (`finalize_early` events); of the 14 with a comparable
  terminal, **`reconciled_match=true` occurred 0 times** and **`extra_words ≥ 1` on all 14**
  (13 × 1 word, 1 × 7 words; `extra_words` sum = 20). i.e. the early snapshot dropped the
  trailing word on **essentially every engagement**.
- **`time_saved_ms` p50 ≈ 99 ms** (min 60, max 988). The lever trades a ~99 ms median tail
  saving for a near-100 % trailing-word drop.

**Verdict: `extra_words` is NOT ≈0 at 300 ms — it is ≈1 per engagement.** This confirms the
STT-013 caveat (Gradium's ~800 ms `delay_in_frames` lookahead buffers the trailing word past
a 300 ms quiet window). The correctness gate (§6 step 3–4, "word-loss rate must be ~0")
**fails at 300 ms**. Recommendation stands: **keep STT-014 default-OFF**, or raise the window
toward the deterministic ~350 ms `flushed` cost (at which point it offers little over the
lossless baseline). A formal WER pass was not run; the reconcile gauge alone is already
decisive against 300 ms. The mechanism + safety instrumentation behaved exactly as designed —
the drop was **observable**, never silent.

### ADR-0029 gate (combined with TASK-BE-020)

**FAIL** in both configs (mouth-to-ear p95 3492 ms BEFORE, 2185 ms AFTER; even the AFTER p50
1919 ms > the 1500 ms gate). The dominant remaining cost is the model first-token
(TASK-BE-033), not the STT finalize tail. Barge-in / US-036 slices showed no regression in
the sample.

Raw evidence: `/tmp/report_before.json`, `/tmp/report_after.json` on the measurement host
(not committed). No numbers fabricated.
