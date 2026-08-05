# BUG-008 — Failed/unavailable TTS turns pollute the `tts_first_audio` p95

## Header

- **Bug ID:** BUG-008
- **Title:** `voice.tts.first_audio` span emitted with total-elapsed on failure/unavailable paths
- **Status:** New
- **Severity:** Medium
- **Priority:** P2
- **Detected by:** Adversarial review
- **Detected date:** 2026-08-05
- **Related user story:** US-040 (streaming TTS) / EPIC-012
- **Related epic:** EPIC-012
- **Branch:** `fix/BUG-008-tts-span-outcome-filter`
- **Owner:** Voice runtime developer

## Problem Statement

The streaming TTS processor emits the `voice.tts.first_audio` timing span on failure and
unavailable paths carrying **total elapsed** time, and `pipeline_timing` groups spans by name
with **no outcome filter** — so non-success turns skew the `tts_first_audio` p95/p99.

## Environment

- **Environment:** local / test
- **Channel:** web voice (streaming TTS)
- **Provider configuration:** Gradium streaming TTS
- **Build or commit:** `feat/sprint-11-remote-deployment`
- **Correlation ID:** n/a

## Reproduction Steps

1. Given a run with some TTS turns that fail or return unavailable.
2. When pipeline timing aggregates `voice.tts.first_audio` across the run.
3. Then failed turns' total-elapsed values are included in the `tts_first_audio` distribution.

## Expected Result

`voice.tts.first_audio` reflects **time-to-first-audio for turns that actually played audio**;
failure/interrupted/unavailable turns do not contribute to that distribution (their elapsed time
belongs on the outcome event, not the first-audio span). This mirrors the fix already applied for
interrupted turns.

## Actual Result

The failure and unavailable branches still emit the span with `total_ms`, and the aggregator does
not filter by outcome, so p95/p99 for first-audio is inflated by non-success turns.

## Evidence

- Code: `voice-agent/web_voice/streaming_tts_processor.py:191-196` and `:218-223` (span emitted
  with `total_ms` on failure/unavailable); success path emits real first-audio at `:204-209`.
- Aggregation with no outcome filter: `voice-agent/voice_common/pipeline_timing.py:102-106`.
- Prior related fix (interrupted turns) recorded in the project learnings.

## Impact

- **operational impact:** misleading latency metrics — the exact number used to judge the
  ADR-0029 gate can be skewed by failures, hiding or faking regressions.
- **latency/SLO impact:** direct — corrupts `tts_first_audio` p95/p99 reporting.
- **customer impact:** none directly (metrics only).

## Acceptance Criteria For Fix

- [ ] `voice.tts.first_audio` is emitted only when audio actually played (real
      time-to-first-audio); failure/unavailable/interrupted paths put elapsed on the outcome
      event instead.
- [ ] `pipeline_timing` `tts_first_audio` reflects success turns only (via emission discipline
      and/or an outcome filter).
- [ ] A regression test asserts a failed TTS turn does not contribute to `tts_first_audio`.
- [ ] Relevant OpenTelemetry traces, metrics and structured logs are present or explicitly not
      applicable.
- [ ] Adversarial code review is at least 90% satisfied.
- [ ] QA retest passes.
- [ ] Related documentation (`voice-journey-timing.md`) updated if behavior changed.

## Developer Notes

- root cause:
- files changed:
- tests added/updated:
- OpenTelemetry added/updated:
- residual risk:

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
