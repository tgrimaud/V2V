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
pilot-latency ahead of billing; add spoken filler phrases to the scope). First ticket done to
the merge-ready gate: **TASK-WEB-019** (generic spoken filler, US-020) on
`task/TASK-WEB-019-filler-phrase` — adversarial review 92/100 + QA GO
(`docs/qa/task-web-019-filler-qa-report.md`), awaiting the user's explicit merge. Remaining:
TASK-WEB-015 (levers) and TASK-WEB-014 live closure.

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
| TASK-WEB-014 | True mouth-to-ear latency instrumentation (already merged) — **closure**: warm live sample vs real backend + adversarial/QA against the ADR-0029 gate | Measure | Merged; pilot closure pending in this sprint |
| TASK-WEB-015 | Perceived-latency optimization levers — backend-stream-to-TTS (first sentence), connect-time STT/LLM warm-up, end-of-turn hold tuning | Optimize | Planned |
| TASK-WEB-019 | Spoken filler / acknowledgement while the answer is being prepared (delivers US-020) | Perceived latency | Merge-ready — V1 generic filler (2026-07-29): adversarial review 92/100, QA GO (`docs/qa/task-web-019-filler-qa-report.md`); merge on user request |

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
