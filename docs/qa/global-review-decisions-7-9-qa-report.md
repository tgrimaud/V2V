# QA Functional And Latency Report — Global-review decisions #7–#9

**Date:** 2026-08-15 (recorded)
**Branch:** `feat/sprint-11-remote-deployment`
**Tickets under test:** TASK-BE-032 (DEC-002 amount matching), TASK-WEB-033 (STT partial-semantics
drift guard), TASK-WEB-034 (`/api/voice/turn` JSON reply)
**Adversarial code review:** 93/100 — Pass (see conversation record); non-blocking cleanups applied
(commit `0859152`).

## Executive Summary

- **Overall readiness:** **GO** (functional). Three focused safety/robustness changes; full automated
  regression green on both tiers; the live `/turn` HTTP contract error path was validated out-of-band;
  net **privacy improvement** (customer text removed from HTTP headers/logs).
- **Main blockers:** none.
- **Residual risks:** DEC-002 amount grounding is exercised only once BSS/PDF evidence carries amounts
  (gated by OQ-003/004); documented amount-parsing heuristics (currency/cents split, lone-separator-3-digits)
  bias toward the **safe/block** side.

## Scope Tested

- **Epics / stories:** EPIC-009 (DEC-002 trust) via TASK-BE-032; EPIC-006 (voice runtime) via
  TASK-WEB-033 / TASK-WEB-034.
- **Channels:** web batch `POST /api/voice/turn`; WebRTC streaming path **unaffected** (each vetted
  sentence still goes straight to the transport track).
- **Providers / fakes:** fixture STT, stub backend, manual domain fakes (no Mockito), in-memory fake
  WebSocket for streaming STT.
- **Environment:** local dev (macOS, Python 3.14 venv, Java/Maven offline `-o`); no network/provider
  dependency.

## Functional Results

| Area | Status | Evidence | Notes |
|---|---|---|---|
| DEC-002: fabricated amount that digit-collides with a grounded one is still blocked | ✅ Pass | `OutputGuardrailTest.digitCollisionBlocked` (`€1.50` vs grounded `150 €` → UNGROUNDED) | Closes the `[^0-9]` collision bypass |
| DEC-002: same amount across locales matches grounded evidence | ✅ Pass | `crossLocaleAmountMatches` (`1.234,56 €` ↔ `€1,234.56` → PASS) | fewer false hand-offs |
| DEC-002: same digits, different currency do not match | ✅ Pass | `differentCurrencyDoesNotMatch` (`50 €` vs `$50` → UNGROUNDED) | currency class is part of the key |
| DEC-002: lone-separator-3-digits read as thousands (documented heuristic) | ✅ Pass | `loneSeparatorThreeDigitsIsThousands` (`1.234 €` == `1234 €`) | documented edge |
| DEC-002: existing grounded/ungrounded/refusal/blank behavior unchanged | ✅ Pass | pre-existing `OutputGuardrailTest` cases still green | no regression |
| STT: normal delta partials report no drift, final = joined delta | ✅ Pass | `test_delta_partials_report_no_cumulative_drift` | live-validated semantics (STT-013) preserved |
| STT: cumulative-looking partials flagged **without** mutating the transcript | ✅ Pass | `test_cumulative_partials_flagged_without_mutating_delta_behavior` | observe, don't mutate |
| STT: drift log carries no transcript (PII-safe) | ✅ Pass | `_note_semantics_drift` logs counts/lengths only; once per session | privacy preserved |
| `/turn`: 200 success returns JSON with base64 WAV + transcript/answer/metadata | ✅ Pass | `test_turn_endpoint_returns_wav_on_pipecat_runtime`, `..._exposes_transcript_and_answer_in_json_body` (real server thread) | uniform success shape |
| `/turn`: degraded mode returns 200 JSON `outcome=degraded` + `degraded_reason` | ✅ Pass | `test_turn_endpoint_speaks_a_degraded_wav_when_the_backend_fails` | safe fallback intact |
| `/turn`: identical audio across stdlib/pipecat runtimes | ✅ Pass | `test_turn_endpoint_returns_identical_wav_across_runtimes` | runtime parity |
| `/turn`: fails-closed error body stays uniform JSON, **no customer text in headers** | ✅ Pass | **live run** on `127.0.0.1:8097`: `502 application/json`, `error_code=fixture_missing`, sanitized `message`, **no `X-Voice*`/`X-Answer*`/`X-Correlation` headers** | validates the privacy/robustness intent end-to-end |
| OpenAPI still describes every voice endpoint after the schema change | ✅ Pass | behave `web_voice.feature` openapi scenario | `TurnSuccessBody` resolves |

**Automated regression:** backend **392** tests + ArchUnit green (`mvn -o test`, BUILD SUCCESS);
voice-agent **504** unit tests green + behave **13 features / 36 scenarios / 169 steps** green.

## Latency Results

| Slice | p50 | p95 | p99 | Sample | Warm/Cold | Notes |
|---|---:|---:|---:|---:|---|---|
| Channel egress (`/turn`) | n/a | n/a | n/a | — | — | Batch endpoint; base64 inflates the wire payload ~1.33× but not a live-voice slice. Not measured (no SLO on the batch fallback). |
| Mouth-to-ear (live) | — | — | — | — | — | Out of scope here; owned by **TASK-WEB-032** (warm co-located WebRTC + real backend vs ADR-0029). These changes don't touch the WebRTC media path. |

No latency regression expected: TASK-BE-032 is a pure in-memory guardrail refinement; TASK-WEB-033 is
counting/logging only; TASK-WEB-034 changes only the batch reply encoding (WebRTC unaffected).

## Component Findings

| Brick | Status | Findings | Next action |
|---|---|---|---|
| Output guardrail (DEC-002) | ✅ | Collision bypass closed; currency-aware, locale-aware key | Confirm definitive rounding/currency policy at BSS amount wiring (OQ-003/004) |
| Streaming STT session | ✅ | Delta semantics preserved; drift observable via `voice.stt.partial_semantics_drift` (+`.count`) | Alert on sustained non-zero drift in prod → revisit finalization |
| Web voice HTTP contract | ✅ | `/turn` uniform JSON; `/tts` keeps raw `audio/wav`; live error path confirmed | — |

## Defects And Gaps

| Severity | Finding | Impact | Owner |
|---|---|---|---|
| Low (accepted) | Currency/cents split (`50 cents` ≠ `€0.50`) and lone-separator-3-digits heuristic can over-block | Extra safe hand-off, never an ungrounded amount voiced | Backend — revisit at BSS wiring |
| Info | Live 200 success over HTTP not reproducible with offline providers (fixture STT resolves by file path, not raw bytes) | None — 200 JSON contract is covered by `test_voice_runtime.py` (real server thread + stub ingress) | QA — covered by automation |

## Open Questions

- **Product:** none new (DEC-002 policy confirmed for V1: block any ungrounded amount).
- **Architecture:** none new.
- **Technical:** definitive amount rounding/currency policy to be finalized when BSS/PDF amounts land
  (OQ-003 / OQ-004).

## Recommendation

- **Go / No-go:** **GO** for these three tickets (functional QA passed; adversarial review ≥ 90).
- **Required fixes before pilot:** none from this scope. Merge remains the user's explicit decision
  (ticket → sprint branch), per the delivery workflow.
