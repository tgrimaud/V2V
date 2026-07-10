# Sprint 2 — STT Hardening

## Sprint Objective

Turn the validated STT slice (Sprint 1) into a **usable quality gate** and complete
the **observability** of the STT path, so pilot readiness can be judged on real,
trustworthy numbers.

This sprint stays strictly within the STT scope: no backend, no TTS/voice-out, no
streaming. It closes the non-blocking follow-ups surfaced by Sprint 1's adversarial
reviews and QA run.

## Status

**Status:** Planned
**Created:** 2026-07-10
**Predecessor:** [`sprint-stt-validation.md`](sprint-stt-validation.md) (Sprint 1 — Done, 2026-07-10)
**Final validator:** User
**Merge rule:** no branch is merged unless the user explicitly asks.

## Roadmap Context

| Sprint | Theme | State |
|---|---|---|
| Sprint 1 | STT validation (fixtures → Gradium transcript, timing, QA) | ✅ Done |
| **Sprint 2** | **STT hardening (this sprint)** | Planned |
| Sprint 3 | TTS / voice-out (batch, non-streaming) → first end-to-end voice loop | Planned |
| Sprint 4 | Latency optimization: streaming STT (TASK-STT-010) + streaming TTS (TASK-WEB-004) | Planned |

## Included Tickets

| Ticket | Title | Type | Priority | Closes | Sprint role |
|---|---|---|---|---|---|
| TASK-STT-011 | Normalize transcripts (case/punctuation/accents) before WER scoring | Technical task | High | RF-008 | Makes the WER quality gate usable against a real engine — top priority |
| TASK-STT-007 | Expand the STT fixture set with multiple samples per category | Technical task | Medium | RF-005 | Statistically meaningful per-category quality + p95/p99 (already In progress) |
| TASK-STT-005 | Redact bare sensitive identifiers in failure sanitization | Technical task | Medium | RF-001 | Hardens sanitization for a real provider adapter |
| TASK-STT-006 | Add a dedicated `UNAVAILABLE` STT outcome | Technical task | Low | RF-004 | Distinguishes "no usable speech" from a processing error |
| TASK-STT-009 | Detect and instrument end-of-turn for the voice journey | Technical task | Medium | US-036 `end_of_turn` gap | Closes the only US-036 slice with no backing ticket |

## Ticket Status

| Ticket | Sprint status | Notes |
|---|---|---|
| TASK-STT-011 | Planned | Do first — several other measurements depend on a trustworthy WER. Re-run the live Gradium manifest afterwards to record realistic per-category WER. |
| TASK-STT-007 | Planned (In progress) | Real single-sample audio already committed; remaining = multiple samples/category, real human noisy/accented recordings, minimum-sample-size rule. Best paired with TASK-STT-011 (re-score on the expanded set). |
| TASK-STT-005 | Planned | Independent; small, well-scoped sanitization change. |
| TASK-STT-006 | Planned | Independent; audit the four telemetry surfaces + quality harness for the new outcome. |
| TASK-STT-009 | Planned | Voice-runtime end-of-turn detection on the web voice stream; emits an OpenTelemetry span consumed by `PipelineTimingReport`. |

## Out Of Sprint

| Ticket | Reason |
|---|---|
| TASK-STT-010 (streaming STT) | Latency optimization — deferred to **Sprint 4**, where it is built together with streaming TTS (TASK-WEB-004) so the chunked/streaming transport is implemented once for both directions. Closes RF-007 there. |
| TASK-WEB-002 / TASK-WEB-003 | TTS voice-out and backend/LLM bridge — **Sprint 3** (voice-out) and backend work, not STT hardening. |
| TASK-WEB-004 (streaming TTS) | Streaming voice-out — **Sprint 4** (latency optimization). |
| RF-006 (web ingress auth) | Gated by OQ-001 (web voice identity) and TASK-WEB-003 (backend orchestration); not an STT-hardening item. |

## Delivery Order

1. **TASK-STT-011** — normalize WER, re-run live Gradium, record realistic per-category WER (unblocks a trustworthy gate).
2. **TASK-STT-007** — expand fixtures per category, re-score with the normalized WER, define the minimum sample size for meaningful p95/p99.
3. **TASK-STT-005** — bare-identifier redaction hardening.
4. **TASK-STT-006** — dedicated `UNAVAILABLE` outcome.
5. **TASK-STT-009** — end-of-turn detection + span, closing the US-036 `end_of_turn` gap.

## Branch Plan

Each ticket is implemented on its own branch (per the repository branching strategy):

| Ticket | Branch |
|---|---|
| TASK-STT-011 | `task/TASK-STT-011-normalize-wer` |
| TASK-STT-007 | `task/TASK-STT-007-expand-fixture-samples` |
| TASK-STT-005 | `task/TASK-STT-005-redact-bare-identifiers` |
| TASK-STT-006 | `task/TASK-STT-006-unavailable-outcome` |
| TASK-STT-009 | `task/TASK-STT-009-end-of-turn-detection` |

## Sprint Acceptance Criteria

```gherkin
Scenario: The STT quality gate is trustworthy
  Given the WER scorer normalizes case, punctuation and accents
  When the live Gradium manifest is re-scored over the expanded fixture set
  Then formatting-only differences score WER 0.0
  And a genuine substitution or omission still increases the WER
  And per-category quality and latency percentiles are reported with a stated sample size
```

```gherkin
Scenario: The STT path is fully observable and safe
  Given a failure reason may contain a bare filename or identifier
  Then the sanitized reason redacts it while keeping the stable error_code
  And silence is reported as UNAVAILABLE rather than a processing error
  And the end_of_turn slice is measured by the US-036 pipeline timing report
```

## Open Questions

- How many samples per category before p95/p99 is reported as meaningful (feeds TASK-STT-007)?
- After removing WER artifacts, does the default `quality_threshold` (0.8) still make sense (feeds TASK-STT-011)?
- Which end-of-turn signal is authoritative for the web path — silence window, VAD, or an explicit client stop (feeds TASK-STT-009)?
