# Sprint 9 — Hardening / Assainissement (accumulated small improvements & set-aside debt)

## Sprint Objective

Pay down the accumulated backlog of small improvements, hardening items and set-aside
follow-ups that piled up across Sprints 2–8 while the team stayed on the critical path
(voice loop → streaming → answer engine → CSV KB). This is a **clean-up / hardening**
sprint: no new product theme, low-to-medium risk items, each closing a known debt or
review finding. Larger themes are pushed one slot: **billing/identity → Sprint 10**,
**telephony/Genesys → Sprint 11**.

This sprint is explicitly **not** the pilot-readiness *latency* sprint (TASK-WEB-014/015
stay out — they are a dedicated pilot-gate theme, though TASK-WEB-017 here unblocks the
per-turn latency measurement they depend on).

## Status

**Status:** In progress (opened 2026-07-23). Scope set by user decision after the Sprint 8
live tests surfaced BUG-005 and TASK-WEB-017. Delivered so far: TASK-WEB-013 + TASK-WEB-017
(both merged); BUG-004 closed (live-validated, fix already merged); TASK-ENV-001 + TASK-STT-012
reconciled as already-delivered; **BUG-005 + TASK-WEB-012/RF-022 implemented** on
`fix/BUG-005-internal-kb-content-leak` (KB audience boundary + weak-confidence clarify band +
env-tunable Python floor; ADR-0034; adversarial 92/100; Java 262 / Python 353 + behave 27 green)
— **pending live voice retest** before merge-ready.

## Roadmap Context

| Sprint | Theme | State |
|---|---|---|
| Sprint 7 | Real answer engine — RAG over the KB (EPIC-005) | ✅ Done (2026-07-20) |
| Sprint 8 | CSV KB ingestion — `CsvArticleConnector` + embedding `DomainClassifier` | ✅ Done (2026-07-23) |
| **Sprint 9** | **Hardening / assainissement — small improvements & set-aside debt — this sprint** | Planned (2026-07-23) |
| Sprint 10 (tentative) | Customer identity + BSS/PDF evidence + deterministic comparison (EPIC-002/003/004) | Planned — gated by OQ-001/003/004 |
| Sprint 11 (tentative) | Telephony channel (US-018) + Genesys advisor handoff (EPIC-007) | Planned — gated by OQ-006 |

## Why now (state that justifies the sprint)

- Eight sprints of critical-path delivery left a tail of small, low-risk items (telemetry
  import symmetry, per-turn telemetry identity, OpenAPI specs, an open stub invariant) that
  never justified their own sprint but degrade consistency and observability if left
  indefinitely. (Two items initially listed here — the venv standardization TASK-ENV-001 and
  the streaming VAD end-of-turn TASK-STT-012 — turned out to be already delivered in
  Sprints 5/6; their stale statuses were reconciled on 2026-07-23.)
- Live Sprint 8 testing surfaced real functional debt: internal KB content leaking to end
  users (BUG-005) and a permissive confidence gate on vague turns (TASK-WEB-012).
- Two P1 bugs are effectively one step from closed (BUG-004 fixed backend-side pending live
  validation) and should not linger across a whole billing sprint.
- Closing this debt before the billing/identity sprint keeps that larger theme clean.

## Tickets

Grouped by tier. Full ticket details live in the linked task files / bug tickets.

### Tier A — small cleanups (low risk, no external gate)

| Ticket | Title | Effort | Entry state |
|---|---|---|---|
| TASK-WEB-013 | Unify telemetry imports (`ingress.py` → `voice_common.telemetry`) — closes RF-023 | S | ✅ Merged into `feat/sprint-9-hardening` (2026-07-23, ff; branch deleted) — one-line import change, 334 unittest + 26 behave green |
| TASK-WEB-017 | Per-turn identity on WebRTC streaming telemetry (keep stable per-conversation `correlation_id`) — enables per-turn latency | M | ✅ Merged into `feat/sprint-9-hardening` (2026-07-27, ff) — recorder turn baggage + `(correlation_id, turn_index)` bucketing + `per_turn` report; unittest 346 (+12) + behave 27 green; adversarial 93/100; QA passed inc. warm **live** Gradium+Mistral multi-turn sample (`docs/qa/task-web-017-per-turn-telemetry-qa.md`) |
| TASK-ENV-001 | Standardize the `voice-agent` test virtualenv | S | ✅ Already delivered (Sprint 5, on restart) — stale status reconciled 2026-07-23, no work needed |
| TASK-STT-012 | Streaming VAD-based end-of-turn detection | S | ✅ Already delivered (Sprint 6, merged to restart — review 93/100 + QA Go) — stale status reconciled 2026-07-23, no work needed |
| RF-017 | Assert the stub DEC-002 no-amount invariant at import time (or close as superseded by the HTTP backend default) | S | Open (Low) |
| RF-019 | Live re-validation of the browser answering loop (Chrome DevTools MCP) — the live stack is already up | S/M | Gated (manual live QA) |

### Tier B — API / documentation hardening

| Ticket | Title | Effort |
|---|---|---|
| TASK-BE-016 | OpenAPI/Swagger for the Java backend (springdoc) | M |
| TASK-WEB-016 | OpenAPI YAML for the Python voice runtime (`web_voice` `/api/voice/*`, hand-written from the HTTP contract doc) | M |

### Tier C — small comfort feature

| Ticket | Title | Effort |
|---|---|---|
| TASK-WEB-010 | End the call on a customer closing formula (US-041) — closing-intent detection + false-positive guard + end-of-call telemetry | M |

### Tier D — set-aside functional debt

| Ticket | Title | Prio | Effort |
|---|---|---|---|
| BUG-004 | LLM intermittently refuses ("transfer to advisor") despite passing evidence | P1 | ✅ Closed (2026-07-27) — fix already merged; live-validated: greeting variant 20/20 grounded (was ~1/7), off-topic refused, DEC-002 preserved, `AnswerLanguageTest` green |
| BUG-005 | Internal agent-facing KB content (R6/ION, VAA) voiced to the end user on a vague turn; weak-but-passing confidence | P1 | ✅ Implemented (2026-07-27) — audience boundary (fail-closed `audience==customer` filter) + 3-band clarify guardrail + vague-turn detection; ADR-0034; adversarial 92/100; tests green. Pending live voice retest |
| BUG-001 | Input guardrail blocks legitimate phishing/scam-call support questions | P2 | M |
| TASK-WEB-012 | Confidence policy for answers — treat a `SUCCESS` answer without confidence as degraded, or require the HTTP backend to emit confidence (closes RF-022/015/018, DEC-002); couples with BUG-005 facet 2 | M | ✅ Implemented (2026-07-27) — backend three-band confidence policy (floor→clarify→answer) + env-tunable Python client floor (RF-022, `VOICE_BACKEND_CONFIDENCE_THRESHOLD`); ADR-0034. Definitive proof threshold value still gated by OQ-002 |

## Out Of Scope (explicitly deferred)

- **TASK-WEB-014 / TASK-WEB-015** — mouth-to-ear latency instrumentation + optimization
  levers: dedicated pilot-readiness latency theme (High, pilot gate), not assainissement.
  TASK-WEB-017 here is their prerequisite (per-turn measurement).
- **RF-021** — `backend.first_token` vs `backend.request`: gated by a streaming backend.
- **Billing / customer identity / BSS / PDF / comparison** — the shifted **Sprint 10**
  (EPIC-002/003/004, gated by OQ-001/003/004).
- **Telephony / Genesys** — the shifted **Sprint 11** (EPIC-007, gated by OQ-006).

## Delivery Notes

- Each ticket keeps its own branch (`task/…`, `fix/BUG-…`) per the delivery workflow;
  adversarial review ≥ 90% then QA before the branch is merge-ready. Merge only on the
  user's explicit request.
- BUG-005 and TASK-WEB-012 are coupled (weak-confidence handling); sequence BUG-005's
  KB-audience boundary and the confidence policy together to avoid a double rework.
- Runtime-affecting tickets (TASK-WEB-010/012/017, BUG-004/005) must add/update the
  required OpenTelemetry traces, metrics and structured logs.
