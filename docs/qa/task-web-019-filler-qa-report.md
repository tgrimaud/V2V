# QA Functional And Latency Report — TASK-WEB-019 (Spoken filler / acknowledgement during long analysis)

## Executive Summary
- **Overall readiness:** **Go** — US-020 is satisfied by the V1 generic filler. When the
  backend answer is not ready by a configurable perceived-wait threshold, the runtime speaks
  one short neutral holding phrase, then the real answer. The filler runs **concurrently** with
  the off-loop backend call and adds no meaningful latency to the real answer (measured ~5 ms).
- **Main blockers:** none.
- **Residual risks (accepted, non-blocking):**
  1. If the filler fires and the answer then resolves to `UNAVAILABLE` (nothing to answer —
     essentially an empty transcript, which is fast and below the threshold), the caller could
     hear the filler followed by silence. Practically unreachable because `UNAVAILABLE` turns
     return well before the threshold; documented in the ticket.
  2. **Live** barge-in during the filler (customer speaks over "un instant…" → bot stops) is
     covered *by design* (the filler is a plain bot `TextFrame`, identical to any bot speech, so
     ADR-0025 interruption applies) and by an automated cancellation regression, but the live
     speaker→mic confirmation is the same manual check as TASK-WEB-008 and is left to the live
     session, not this deterministic ticket.
  3. Pilot wording of the phrases and the default threshold (1200 ms) are Product/UX decisions;
     they are env-tunable and must be confirmed with Product before pilot.

## Scope Tested
- **Epics / stories:** EPIC-006 (Voice2Voice) + EPIC-010 (observability, latency) — **US-020**
  (quick spoken acknowledgement during long analysis).
- **Ticket:** TASK-WEB-019 — runtime-local timer filler (Flow A, no broker, ADR-0036).
- **Channels:** voice (shared `AnswerProcessor`, so both the WebRTC streaming and stdlib paths).
- **Providers / fakes:** deterministic fake backends (fast / slow / raising); no live engine
  needed for the contract. Telemetry via the in-memory `TelemetryRecorder`.
- **Environment:** `voice-agent/.venv`, offline, macOS. Suite: 416 unittests + 12 Behave
  features / 33 scenarios (full suite green).

## Functional Results
| Area | Status | Evidence | Notes |
|---|---|---|---|
| US-020 AC — slow analysis gives a short spoken acknowledgement, then the reliable answer | ✅ Pass | Behave `filler.feature` scenario 1; `test_slow_answer_speaks_the_filler_before_the_answer` (order = filler → answer) | Filler fires only past the threshold |
| Fast turns are not padded with a filler | ✅ Pass | Behave `filler.feature` scenario 2; `test_fast_answer_skips_the_filler` | Below threshold → answer only |
| Acknowledgement carries no billing content (DEC-002) | ✅ Pass | `test_filler_carries_no_billing_content_dec_002`; `test_digit_bearing_phrases_are_dropped_dec_002`; import-time assert on built-in phrases | Any digit-bearing override phrase is dropped |
| At most one filler per turn | ✅ Pass | Single timed push in `_run_filler`; slow-turn test emits exactly `[filler, answer]` | No repetition |
| Interruptible (barge-in) | ✅ Pass (by design + regression) | Plain `TextFrame` → normal bot speech (ADR-0025); `test_cancellation_mid_wait_drops_the_pending_filler` proves no out-of-turn filler on cancel | Live speaker→mic check deferred (as TASK-WEB-008) |
| Configurable / disableable | ✅ Pass | `test_disabled_filler_never_speaks_even_when_slow`; `resolve_filler_threshold_ms` / `filler_enabled` / `resolve_filler_phrases` tests | Env: `VOICE_FILLER_ENABLED/_THRESHOLD_MS/_PHRASES` |
| Real answer still served (incl. degraded fallback) after a filler | ✅ Pass | Existing degraded/confidence tests unchanged; answer push path untouched | Filler never replaces the answer |

## Latency Results
Perceived-latency feature: the relevant metrics are (a) how promptly the filler fires once the
threshold passes and (b) that the filler does **not** delay the real answer. Deterministic
measurement, N=20, fake slow backend = 300 ms, threshold = 50 ms:

| Slice | p50 | p95 | max | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| Filler fire offset (turn start → filler spoken) | 51.3 ms | 51.6 ms | 51.6 ms | 20 | warm | Fires right at the configured threshold |
| Answer pushed offset (turn start → real answer) | 304.8 ms | 305.7 ms | 305.7 ms | 20 | warm | ≈ backend delay → **+~5 ms** vs no filler (concurrency proven) |
| Reported `wait_ms` (telemetry) | 50 | 50 | 50 | 20 | warm | Constant = configured threshold, by design |

- **Mouth-to-ear / end-to-end voice latency:** *not measured here* — that is TASK-WEB-014's
  live closure against the ADR-0018/ADR-0029 gates. This ticket only proves the filler is
  concurrent and threshold-accurate; it does not change the real-answer pipeline slices.

## Component Findings
| Brick | Status | Findings | Next action |
|---|---|---|---|
| `voice_pipeline/filler.py` (config + phrases + DEC-002 guard) | ✅ | Env parsing fails safe; digit phrases dropped; built-in set asserted digit-free at import | none |
| `AnswerProcessor` filler orchestration | ✅ | Concurrent timer via `asyncio.Event`; race-guarded; plain `TextFrame`; barge-in-safe cancellation in `finally` | none |
| Observability (`voice.filler.spoken` event + `.count` metric) | ✅ | Carries `correlation_id`, `channel`, `provider`, `wait_ms`; per-turn baggage merged when set; real `tts_first_audio` span untouched | none |

## Defects And Gaps
| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Low | `UNAVAILABLE` after a fired filler → filler + silence (see residual risk 1) | Practically unreachable (UNAVAILABLE is fast) | Dev (accepted) |
| Info | Live barge-in-over-filler confirmation deferred to a live session | Same manual check as TASK-WEB-008 | QA (live) |

## Open Questions
- **Product:** confirm the pilot phrase wording and the default 1200 ms threshold before pilot.
- **Architecture:** none — trigger transport settled in ADR-0036 (+ implementation addendum).
- **Technical:** none.

## Recommendation
- **Go / No-go:** **GO** — QA gate passed. Adversarial review 92/100 (one barge-in cleanup
  finding found and fixed). Functional ACs covered by Behave + unit tests; observability present;
  perceived-latency behaviour measured (concurrent, ~5 ms overhead).
- **Required fixes before pilot:** none from QA. Confirm phrase wording/threshold with Product;
  run the live barge-in-over-filler check during the TASK-WEB-014 live session.
- **Merge:** branch is **merge-ready**; merge only on the user's explicit request.
