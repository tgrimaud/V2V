# BUG-017 - Anomalous barge-in count (45) across 10 headless WebSocket turns

## Header

- **Bug ID:** BUG-017
- **Title:** `barge_in_count=45` over 10 headless WS turns — barge-in fires with no second speaker
- **Status:** New
- **Severity:** Medium
- **Priority:** P2
- **Detected by:** QA (latency measurement, TASK-WEB-039)
- **Detected date:** 2026-08-26
- **Related user story:** US-021 (barge-in) / US-036 (per-slice timing)
- **Related epic:** EPIC-006
- **Branch:** `fix/BUG-017-barge-in-count-anomaly`
- **Owner:** Voice runtime developer

## Problem Statement

During the v0.6.0 pilot WS-live latency measurement (TASK-WEB-039), the server-side telemetry
reported **45 barge-in events across 10 headless turns (~4.5 per turn)**, even though the
headless client sends a single audio clip followed by trailing silence, then holds the call
idle for ~12 s with no further audio. Barge-in should not trigger during the idle hold.

## Environment

- **Environment:** pilot (eir-ai4cc-tst), direct-to-bridge (no HAProxy)
- **Channel:** web voice (WebSocket transport, ADR-0043/0046)
- **Provider configuration:** Gradium streaming STT/TTS + Mistral RAG backend, co-located on the bridge
- **Build or commit:** voice image `0.6.0` (`websocket=on:8091`); branch `task/TASK-WEB-037-websocket-primary-transport`
- **Client:** `scripts/ws_live_client.py --hold 12`, fixture `fixtures/long/billing-question.pcm`
- **Correlation ID:** per-turn dumps in the TASK-WEB-039 telemetry sample (`/tmp/ws-telemetry.jsonl`)

## Reproduction Steps

1. Given a bridge published on `:8091` with the WS control-signal seam active (TASK-WEB-029).
2. When 10 warm headless turns are driven via `ws_live_client.py` (one clip + trailing silence + 12 s idle hold each).
3. Then `streaming_latency_report.py` reports `barge_in_count = 45` for the sample.

## Expected Result

Barge-in fires only when the caller actually speaks over the bot. A headless turn with a single
clip and no overlapping second utterance should produce **0** barge-in events (or exactly the
intended count if the clip legitimately overlaps bot audio).

## Actual Result

~4.5 barge-in events per turn, including during the silent idle hold when the client sends no audio.

## Evidence

- Metrics or latency sample: `barge_in_count: 45` in the TASK-WEB-039 aggregate report; raw per-turn dumps in the sample JSONL.
- Trace/span link: barge-in / control-signal events in the per-call telemetry dumps.

## Impact

- customer impact: on a live call, spurious barge-in would cut the bot's own answer (self-interruption), degrading UX — the same class of issue as the AEC/echo self-interrupt (ADR-0025 point 7), but here with **no** second speaker at all.
- latency or SLO impact: pollutes the barge-in metric and can distort turn accounting in the latency report.
- pilot-readiness impact: undermines confidence in the interruption telemetry until explained.

## Candidate causes (to confirm, not assume)

1. WS control-signal / end-of-turn detector re-arming on the trailing-silence boundary and emitting repeated onset events.
2. The bot's own output audio (TTS) leaking into the onset detector on the WS path (playback→detector loop), analogous to the WebRTC echo self-interrupt but without a mic.
3. Measurement/aggregation artifact — barge-in events counted per pipeline segment or accumulated across turns in one envelope rather than reset per turn.

## Acceptance Criteria For Fix

- [ ] Root cause identified (detector re-arm vs output-audio feedback vs counting artifact).
- [ ] A headless single-clip turn with an idle hold produces the correct barge-in count (0 unless a real overlap is injected).
- [ ] A regression test covers the WS barge-in count over an idle hold.
- [ ] Relevant OpenTelemetry events/metrics are present or corrected (`voice.ws` control signals, barge-in event).
- [ ] Adversarial code review is at least 90% satisfied.
- [ ] QA retest passes (re-run the TASK-WEB-039 style sample; count is sane).

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
