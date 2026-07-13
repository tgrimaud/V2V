# Sprint 2 — STT Hardening

## Sprint Objective

Turn the validated STT slice (Sprint 1) into a **usable quality gate** and complete
the **observability** of the STT path, so pilot readiness can be judged on real,
trustworthy numbers.

This sprint stays strictly within the STT scope: no backend, no TTS/voice-out, no
streaming. It closes the non-blocking follow-ups surfaced by Sprint 1's adversarial
reviews and QA run.

## Status

**Status:** In progress (started 2026-07-10) — 4/5 tickets done (TASK-STT-011/007/005/006), 1 planned (TASK-STT-009)
**Created:** 2026-07-10
**Predecessor:** [`sprint-stt-validation.md`](sprint-stt-validation.md) (Sprint 1 — Done, 2026-07-10)
**Working branch:** `feat/sprint-2-stt-hardening` (from `feat/restart-from-scratch`)
**Final validator:** User
**Merge rule:** no branch is merged unless the user explicitly asks.
**Adversarial review:** run after the first three tickets; findings RF-009/010/011 raised and resolved on `task/sprint-2-review-remediation` (merged).

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
| TASK-STT-011 | ✅ Done (2026-07-10) | `normalize_transcript` folds case/punctuation/accents before WER; 55 unit tests green. Live Gradium re-run: `short` WER 1.00→0.00, `long` 0.083, `accented` 0.182 pass; only `noisy` (0.40) fails on a genuine error (→ TASK-STT-007). Threshold kept at 0.8. |
| TASK-STT-007 | ✅ Done (2026-07-10) | Expanded to 22 fixtures (5/usable category, varied voices, padded onsets); per-category aggregation + `MIN_SAMPLES_FOR_PERCENTILES=5` significance flag; live Gradium per-category run recorded. Closes RF-003 + RF-005. Residual (documented open risk, not blocking): real human recordings for `short`/`noisy`. |
| TASK-STT-005 | ✅ Done (2026-07-10) | `sanitization.py` now redacts bare filenames (`<redacted-file>`) and identifier-like tokens (`<redacted-id>`: UUID, secret prefixes, digit runs, mixed ids) on top of paths; words/dates preserved; `error_code` + length cap kept. Dedicated `test_sanitization.py` (13 tests). Closes RF-001. |
| TASK-STT-006 | ✅ Done (2026-07-13) | `SttOutcome.UNAVAILABLE` + provider-agnostic `NoSpeechDetectedError`; runner maps no-speech to `unavailable` across all four telemetry surfaces (`stt.unavailable` event, `info` log, `error_code=no_speech`, span/completed `outcome=unavailable`); quality harness note + behave scenario tightened to assert `unavailable`. 77 unit + 8 behave green. Closes RF-004. |
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

The sprint branch `feat/sprint-2-stt-hardening` is cut from
`feat/restart-from-scratch`. Each ticket is developed on its **own branch cut from
the sprint branch** and merged back into it once validated (per the repository
branching strategy):

| Ticket | Branch | Status |
|---|---|---|
| TASK-STT-011 | `task/TASK-STT-011-normalize-wer` | ✅ merged into sprint branch |
| TASK-STT-007 | `task/TASK-STT-007-expand-fixture-samples` | ✅ merged into sprint branch |
| TASK-STT-005 | `task/TASK-STT-005-redact-bare-identifiers` | ✅ merged into sprint branch |
| Review remediation | `task/sprint-2-review-remediation` | ✅ merged (RF-009/010/011) |
| TASK-STT-006 | `task/TASK-STT-006-unavailable-outcome` | ✅ done (awaiting merge into sprint branch) |
| TASK-STT-009 | `task/TASK-STT-009-end-of-turn-detection` | pending |

> Docs/knowledge chores (`chore/self-contained-guidance`,
> `chore/generalize-knowledge-session`) were also cut from and merged back into the
> sprint branch during the sprint.

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

- ~~How many samples per category before p95/p99 is reported as meaningful?~~ **Partly answered (TASK-STT-007):** `MIN_SAMPLES_FOR_PERCENTILES = 5` is the reporting floor below which a category is flagged not significant; but 5 is not enough for stable p95/p99 (nearest-rank p95 of 5 ≈ max). Real trust needs many more samples **and** real human recordings — still open.
- ~~After removing WER artifacts, does the default `quality_threshold` (0.8) still make sense?~~ **Answered (TASK-STT-011):** yes — 0.8 cleanly separates good transcripts (short/long/accented ≥ 0.82) from the genuinely degraded noisy sample (0.60). Kept.
- Which end-of-turn signal is authoritative for the web path — silence window, VAD, or an explicit client stop (feeds TASK-STT-009)?
