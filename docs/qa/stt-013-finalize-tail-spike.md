# TASK-STT-013 — STT post-EOT finalize-tail spike

**Ticket:** TASK-STT-013 (Reduce STT post-EOT finalize tail to meet ADR-0018)
**Related:** ADR-0018 (pilot latency criterion), ADR-0023 (streaming STT transport), US-036, TASK-WEB-009 (baseline)
**Date:** 2026-07-17
**Branch:** `task/TASK-STT-013-reduce-finalize-tail`
**Tool:** `voice-agent/scripts/stt013_finalize_spike.py`
**Verdict:** **GO** — `time_to_first_audio` p95 < 800 ms is reachable, with **zero transcript loss**, by finalizing on Gradium's `flushed` acknowledgement instead of the terminal `end_of_stream`.

## Why a spike first

The TASK-WEB-009 warm baseline (`streaming-latency-warm-sample.json`) put
`time_to_first_audio` at **p50 1310 ms / p95 1698 ms** — NO-GO on the ADR-0018
criterion (`p95 < 800 ms`). The dominant slice was the STT post-end-of-turn
finalize tail (p95 ~1389 ms), which alone exceeds the whole budget. Before writing
any optimization, we probed *what the tail is actually made of* against live
Gradium, following the project's "live spike before build" discipline.

## Method

`stt013_finalize_spike.py` streams a real PCM clip to Gradium's WebSocket ASR
(`wss://api.gradium.ai/api/speech/asr`), **real-time paced** to emulate a live mic.
At the end it sends `flush` + `end_of_stream` (= our end-of-turn) and timestamps,
relative to the flush, every server message: each `text` partial, `end_text`,
`flushed` (the ack of our `flush_id`), and the terminal `end_of_stream`. It also
compares the transcript already in hand at flush vs the authoritative final.

## Finding: the tail is ~680 ms of *waiting after the transcript is already complete*

Live, real key, 3 clips (short / long / noisy), highly stable across runs:

| Event after flush (EOT) | Timing (after flush) | State |
|---|---:|---|
| last `text` (final word) | ~60–204 ms | **full transcript already received** |
| `flushed` (ack of our `flush_id`) | **~348–353 ms** (stable, clip-length-independent) | deterministic "all pending audio transcribed" signal |
| `end_of_stream` (what the code currently blocks on) | **~775–785 ms** | terminal — adds ~430 ms of pure waiting after `flushed` |

Per-clip summary (`pure_tail` = flush → `end_of_stream`):

| Clip | length | last_text@ | flushed@ | pure_tail (end_of_stream@) |
|---|---:|---:|---:|---:|
| `long/invoice-breakdown` | 5.45 s | ~97 ms | ~347 ms | ~775 ms |
| `short/question` | — | ~64 ms | ~350 ms | ~782 ms |
| `noisy/monthly-amount` | — | ~204 ms | ~350 ms | ~780 ms |

The final transcript is just `" ".join(parts)` of the `text` partials, and the
**last partial always arrives well before `flushed`** (≤204 ms < ~350 ms). So by
`flushed` (~350 ms) the transcript is complete; the remaining ~430 ms until
`end_of_stream` is spent waiting for a terminal handshake we do not need.

## Options considered

| Option | STT tail | Transcript loss | Verdict |
|---|---:|---|---|
| Wait for `end_of_stream` (current) | ~780 ms | none | Baseline — busts the budget |
| **Finalize on `flushed`** | **~350 ms** | **none** | **Chosen** — deterministic, clip-length-independent, no accuracy cost |
| Commit-on-last-partial at flush | ~100 ms | **1 word** (`facture?`) every run | Rejected — drops the trailing word (the ~800 ms `delay_in_frames` lookahead lands after flush) |
| `delay_in_frames` tuning | smaller | accuracy cost | Deferred — a further lever, not needed to pass the gate |
| Debounce on last-text quiet period | ~150–250 ms | none (heuristic) | Deferred follow-up — extra margin if `flushed` proves borderline |

Root cause of why commit-on-last-partial is lossy: Gradium runs with
`delay_in_frames=10` (~800 ms lookahead), so the last ~word of speech is still
buffered as context at flush and is only emitted during the tail. `flushed` waits
for that flush to complete, so it is emitted *after* the trailing word — which is
exactly why it is both fast (~350 ms) and lossless.

## Measured impact — live WebRTC re-measurement (post-fix)

Implemented (finalize on `flushed`) and re-measured over the real WebRTC streaming
path, warm, 8 turns, Gradium streaming STT+TTS, backend stub
(`streaming-latency-warm-postfix.json`):

| Slice | Before (TASK-WEB-009) | After (this fix) |
|---|---:|---:|
| `stt` post-EOT tail (p50 / p95) | 866 / **1389** ms | 371 / **374** ms |
| `tts_first_audio` (p50 / p95) | 309 / 479 ms | 457 / 484 ms |
| `backend_first_token` | ~0 ms (stub) | ~0 ms (stub) |
| **`time_to_first_audio` (p50 / p95)** | 1310 / **1698** ms | 827 / **853** ms |
| ADR-0018 gate (`p95 < 800 ms`) | FAIL (−898 ms) | **FAIL (−53 ms)** |

The STT lever worked exactly as the spike predicted: the tail is now a stable
~373 ms (the ~350 ms `flushed` round-trip) and no longer dominates. **Composite
`time_to_first_audio` p95 dropped from 1698 ms to 853 ms — a 845 ms / ~50 % cut.**

## Residual gap — now TTS-bound, not STT-bound

The gate misses by **53 ms**, now bottlenecked by `tts_first_audio` (p95 484 ms).
The streaming TTS processor starts its `voice.tts.first_audio` timer *before*
`await provider.open()`, so the span includes a **fresh TTS WebSocket connect +
setup every turn**. Measured directly (6 runs):

- TTS `open()` (connect + setup): **~90 ms** warm (~188 ms cold first call).
- first chunk after open: ~236–384 ms (inherent Gradium TTS first-chunk latency).

Pre-warming / reusing the TTS WebSocket so the ~90 ms connect is off the per-turn
critical path would bring `tts_first_audio` p95 ~484 → ~394 ms and **composite p95
~853 → ~763 ms → PASS**. This is a TTS-side change (TASK-WEB-004 streaming-TTS
scope), tracked as a follow-up (**TASK-WEB-011**), not part of the STT finalize
tail. Finalizing STT earlier than `flushed` (last-text debounce) is not a reliable
lever here: the last partial lands at ~97–204 ms but a safe debounce window makes it
no better than the deterministic ~350 ms `flushed` ack, for added accuracy risk.

## Verdict recap

- **STT finalize tail: solved** — `flushed`-based finalization, zero word loss, tail
  ~1389 → ~374 ms p95; TASK-STT-013's objective is met.
- **ADR-0018 pilot gate: not yet met (−53 ms)** — the remaining lever is TTS
  connection pre-warm (TASK-WEB-011), not further STT work.

## Design decision for the implementation

- In `GradiumStreamingSession`, resolve `wait_final()` on the **`flushed`** message
  that matches the `flush_id` we sent, consolidating the transcript from the
  partials received so far. Keep `end_of_stream` (and `error`) as a **fallback**
  terminal so a provider that never sends `flushed` still finalizes safely.
- No change to the safety invariants: transcript is still the concatenation of real
  partials (no invention), the API key is never logged, and an error/drop still
  surfaces `StreamingSttError`.
- Provider-agnostic seam is unchanged; the batch REST provider is untouched.

## Status of the implementation

1. ✅ Finalize-on-`flushed` in `stt_validation/streaming.py` + fake-WS unit tests
   (flushed → final; end_of_stream fallback; error/drop still fail).
2. ✅ Live WebRTC re-measurement (`streaming-latency-warm-postfix.json`): STT tail
   ~374 ms p95; `time_to_first_audio` p95 853 ms (was 1698 ms). Gate still −53 ms,
   now TTS-bound.
3. ✅ ADR-0018 evidence + streaming QA report updated with the post-fix baseline.
4. ✅ Follow-up **TASK-WEB-011** (delivered 2026-07-17) — TTS WebSocket pre-warmed off
   the per-turn critical path; `tts_first_audio` p95 484 → 381 ms, `time_to_first_audio`
   p95 853 → **761.5 ms → GATE MET** (+38.5 ms). See
   [`streaming-latency-warm-prewarm.json`](streaming-latency-warm-prewarm.json).
