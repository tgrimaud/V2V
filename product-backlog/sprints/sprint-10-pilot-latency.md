# Sprint 10 — Pilot-readiness Latency & Perceived Latency

## Sprint Objective

Make the voice loop feel fast enough for a pilot. This sprint owns the **pilot-readiness
latency** theme that was deliberately kept out of the Sprints 6–9 critical path. It has two
complementary goals:

1. **Measured latency** — finish validating true mouth-to-ear latency against the ADR-0029
   gate with a warm live sample and land the concrete optimization levers.
2. **Perceived latency** — when the real answer genuinely needs time (backend + LLM + TTS),
   keep the caller informed with a short spoken acknowledgement so the wait feels responsive
   rather than dead.

This sprint is **off the billing theme**. It was promoted ahead of billing/identity by user
decision on 2026-07-29, shifting **billing/identity → Sprint 11** and **telephony/Genesys →
Sprint 12**.

## Status

**Status:** In progress (started 2026-07-29). Scope set by user decision 2026-07-29 (promote
pilot-latency ahead of billing; add spoken filler phrases to the scope).

**Sprint branch:** `feat/sprint-10-pilot-latency` (off `feat/restart-from-scratch`). Adopting the
**two-level branch model** (decision 2026-07-29): ticket branches fork from and merge back into
this sprint branch (`git merge --no-ff`); the sprint branch merges into `feat/restart-from-scratch`
only at sprint closure, on the user's explicit request. See `docs/operations/development-workflow.md`.

First ticket integrated into the sprint branch: **TASK-WEB-019** (generic spoken filler, US-020) —
adversarial review 92/100 + QA GO (`docs/qa/task-web-019-filler-qa-report.md`), merged into
`feat/sprint-10-pilot-latency`. In progress: **TASK-WEB-015** on `task/TASK-WEB-015-latency-levers` —
**lever 3 delivered + live-accepted** (env-tunable end-of-turn hold; live pass 2026-07-29 = −150 ms
deterministic 500→350, 0 false-cut, tuned default 350 ms recommended), **levers 1 & 2 designed**
(ADR-0037), gated on the DEC-002 vetted-stream backend contract + the TASK-WEB-014 live baseline.

**Live pilot pass 2026-07-29 (TASK-WEB-014 measurement closure).** A warm live sample against the
**real backend** (streaming WebRTC, headphones) measured mouth-to-ear `voice_to_first_audio` p95
**≈ 4.1–4.4 s** and `time_to_first_audio` p95 **≈ 3.8–3.9 s** → **ADR-0029 gate FAIL** (criteria
≤ 1.5 s / ≤ 1.2 s), dominated by the serial STT (~1 s p50) + backend first-token (~1 s p50) slices;
TTS is flat (pre-warmed). This is the honest pilot number TASK-WEB-014 was missing → **NO-GO on the
latency gate as-is**, fix path = TASK-WEB-015 **levers 1 (SSE first-sentence → TTS) + 2 (connect-time
warm-up)**, now confirmed as the decisive work. The spoken filler (TASK-WEB-019) fired live on the
slowest turns without skewing `tts_first_audio`. Write-up + evidence:
`docs/qa/streaming-voice-qa-report.md` (Live Pilot Pass 2026-07-29),
`docs/qa/streaming-latency-eot{500,350}-live-2026-07-29.json`. Remaining: TASK-WEB-015 levers 1 & 2
(live before/after) + formal adversarial/QA sign-off of the TASK-WEB-014 closure.

## Roadmap Context

| Sprint | Theme | State |
|---|---|---|
| Sprint 8 | CSV KB ingestion | ✅ Done (2026-07-23) |
| Sprint 9 | Hardening / assainissement | ✅ Done (2026-07-28) |
| **Sprint 10** | **Pilot-readiness latency & perceived latency — this sprint** | In progress (started 2026-07-29) |
| Sprint 11 (tentative) | Customer identity + BSS/PDF evidence + deterministic comparison (EPIC-002/003/004) | Planned — gated by OQ-001/003/004 |
| Sprint 12 (tentative) | Telephony channel (US-018) + Genesys advisor handoff (EPIC-007) | Planned — gated by OQ-006 |

## Why now (state that justifies the sprint)

- The streaming loop meets the ADR-0018 first-audio gate on fixtures, but true mouth-to-ear
  latency (TASK-WEB-014) still needs a **warm live sample vs the real backend + adversarial/QA**
  before any pilot latency claim.
- The optimization levers (TASK-WEB-015) were scoped from the Sprint 7 demo baseline (cold
  ~2.95 s / warm ~2.50 s to first audio) but never implemented; they are the concrete way to
  cut perceived wait.
- Even with the levers, a KB-grounded billing answer can exceed a comfortable silent-wait
  threshold. US-020 (a quick spoken acknowledgement during long analysis) is the product
  answer to that and is still unimplemented — it belongs with the latency theme, not billing.
- Doing this before billing means the billing sprint is validated on a loop that already feels
  responsive, instead of discovering perceived-latency problems on top of new billing logic.

## Tickets

| Ticket | Title | Role | Status |
|---|---|---|---|
| TASK-WEB-014 | True mouth-to-ear latency instrumentation (already merged) — **closure**: warm live sample vs real backend + adversarial/QA against the ADR-0029 gate | Measure | **Live sample captured 2026-07-29**: mouth-to-ear p95 ≈ 4.1–4.4 s → **ADR-0029 gate FAIL** (NO-GO as-is); fix path = WEB-015 levers 1 & 2. Formal adversarial/QA sign-off pending |
| TASK-WEB-015 | Perceived-latency optimization levers — backend-stream-to-TTS (first sentence), connect-time STT/LLM warm-up, end-of-turn hold tuning | Optimize | **Lever 3 done + live-accepted** (−150 ms, 0 false-cut, tuned default 350 ms). Levers 1 & 2 **split out** into TASK-WEB-020 / TASK-WEB-021 (+ backend TASK-BE-017) on 2026-07-29 |
| TASK-WEB-020 | Lever 1 — stream the backend answer to TTS on the first vetted sentence (consume `converse-stream` SSE instead of blocking `/converse`) | Optimize | **Implemented, ready for review + live pass** — flag `VOICE_BACKEND_STREAM` default-off; per-sentence DEC-002 confirmed on the backend stream; confidence policy = option A (advisory); barge-in aborts + closes socket; `backend.first_token` now = first sentence. Tests green (unittest 462, behave 13·36·169). Gate to enable: warm+cold live before/after vs TASK-WEB-014 baseline, ADR-0029 re-check |
| TASK-WEB-021 | Lever 2 — connect-time warm-up of the STT session + first LLM/embedding call (mirror `TtsSessionWarmer`) | Optimize | **Runtime implemented 2026-07-29, adversarial review fixes applied** — shared `SessionWarmer` pre-opens STT at connect (no leak; **opt-in `VOICE_STT_PREWARM=1`, off by default**) + non-blocking `backend.warm_up()` trigger (`POST /warm-up`, `VOICE_BACKEND_WARMUP` on); telemetry `voice.backend.warmup` + `voice.stt.prewarm`; unittest 442 / behave 33 green. **Live turn-1 sample 2026-07-30** (real backend via BE-017 worktree): warmup=success + prewarm=hit (Gradium keeps idle socket, no fallback/leak); backend cold penalty bounded +448 ms→~300 ms residual (8.5 s cold outlier avoided); m2e p95 −390 ms (noisy); **turn-1-only, ADR-0029 gate still needs lever 1**. Follow-up: warm full converse path. **Validated by user 2026-07-30, checks re-run green (unittest 442 / behave 12·33·154) → merge-ready (merge on explicit request)** |
| TASK-BE-017 | Backend support for the levers — warm-up path (lever 2) + vetted-stream contract test / optional early confidence (lever 1) | Enable | To do — backend dependency of TASK-WEB-020/021 |
| TASK-WEB-019 | Spoken filler / acknowledgement while the answer is being prepared (delivers US-020) | Perceived latency | Integrated into `feat/sprint-10-pilot-latency` (2026-07-29): adversarial review 92/100, QA GO (`docs/qa/task-web-019-filler-qa-report.md`); sprint→delivery merge at sprint closure on user request |

Full ticket details live in `tasks/web-voice-tasks.md`.

## Out Of Scope

- Billing/identity, BSS/PDF evidence and deterministic comparison (Sprint 11, gated by
  OQ-001/003/004).
- Telephony and Genesys handoff (Sprint 12, gated by OQ-006).
- Any change to what the bot *says* about a bill; this sprint only changes *how fast* and *how
  responsively* it speaks, never the billing content (DEC-002 stays enforced).

## Exit Criteria

- TASK-WEB-014 closed with a warm **live** mouth-to-ear sample (p50/p95/p99 by slice) evaluated
  against the ADR-0029 gate, plus adversarial review ≥ 90% and QA GO.
- TASK-WEB-015 levers implemented and measured against the same baseline, with the observed
  before/after delta reported per slice.
- TASK-WEB-019 delivers US-020: a short spoken acknowledgement fires only when the wait exceeds
  the configured threshold, barge-in still works, no fabricated billing content, and the
  behaviour is observable via telemetry.
- Each ticket passes adversarial review ≥ 90% then QA before the branch is merge-ready. Merge
  only on the user's explicit request.

**Progress (2026-07-29).** TASK-WEB-014 live mouth-to-ear sample **captured** (real backend) →
ADR-0029 gate **FAIL** (p95 ≈ 4.1–4.4 s; the measurement bar is met, the latency bar is not —
NO-GO as-is). TASK-WEB-015 **lever 3 measured before/after** (−150 ms deterministic, 0 false-cut,
tuned default 350 ms). Still open for exit: TASK-WEB-015 levers 1 & 2 (live before/after) — the
decisive latency work — and the formal adversarial/QA sign-off of the TASK-WEB-014 closure.
