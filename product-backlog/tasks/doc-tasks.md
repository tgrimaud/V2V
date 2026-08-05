# Documentation Technical Tasks

Cross-cutting documentation reconciliation tasks. Documentation under `docs/` must
be written in English (see `.cursor/skills/technical-writer/SKILL.md`).

| Task | Trigger | Status |
|---|---|---|
| TASK-DOC-001 | Full-branch code review after Sprint 5 | Done (2026-07-15) — tracked in `backlog-index.md` |
| TASK-DOC-002 | Full adversarial code+doc review after Sprint 9 | ✅ Done (2026-07-28) — merged into `feat/restart-from-scratch` |

---

## TASK-DOC-002 - Reconcile Stale "Current-State" Documentation After Sprint 9

**Parent:** EPIC-001 (Product and architecture baseline)
**Related decision:** DEC-010 (measure before claiming), documentation-in-English rule
**Related review:** `docs/architecture/reviews/full-adversarial-review-2026-07-28.md`
(full adversarial code + documentation review; drift register D1–D14)
**Classification:** Documentation
**Status:** ✅ Done (2026-07-28) — validated and merged into `feat/restart-from-scratch`
(fast-forward `24995a9..4770ee0`, 15 files); ticket branch deleted (local + remote).
**Priority:** Medium
**Branch:** `task/TASK-DOC-002-doc-drift` (merged, deleted)

### Objective

Bring the top-level "current-state" documentation back in line with the code
delivered through Sprint 9. The full adversarial review found that nearly every
entry document still claimed the Java backend, React frontend and Docker Compose
were **removed** and that **only the STT-validation slice was built**, while on this
branch the backend runs (305 unit tests), the full streaming Voice2Voice loop and
RAG answer engine exist, and `docker-compose.yml` is present. This is a
correctness-of-record failure: it misleads every human and agent onboarding to the
project. TASK-DOC-001 did the equivalent refresh after Sprint 5; Sprints 6–9 drifted
the same docs again.

This task is **documentation-only** and not runtime-affecting (no OpenTelemetry
impact).

### Scope (drift register D1–D14)

- **D1** `README.md` — "removed" claim → two-service rebuilt stack + `docker-compose.yml` present; only React `frontend/` un-rebuilt.
- **D2** `docs/architecture/architecture.md` — branch note "not built yet: Java backend / RAG / streaming / WebRTC (Sprint 6)" → built through Sprint 9; flag legacy route/port tables further down.
- **D3** `docs/architecture/adrs/README.md` — "only the STT-validation slice is built" note → built vs target-only ADR split.
- **D10** `docs/architecture/adrs/README.md` — missing **ADR-0032** row (index jumped 0030 → 0033).
- **D4** `docs/README.md` — "only runnable code is voice-agent Sprints 1–5" → two-service stack.
- **D5/D11/D12/D13** `docs/engineering/development-guide.md` — "only Python slice runnable" banner; add a rebuilt-backend subsection (port **8080**, `/api/conversation/converse` family, split config classes); strengthen the legacy-`main` disclaimer so its `:8081`, `/ask*`, `/seed`, `agent/bot.py` names are not copied.
- **D6** `docs/operations/backlog.md` — "only STT-validation slice delivered" → two-service stack; V1 Core (BSS/PDF/comparison) still target.
- **D7** `docs/product/v1-scope.md` — "only STT validation built; no TTS" → full loop + RAG built; latency slices instrumented.
- **D8** `docs/architecture/channel-identity-boundary.md` — "only STT-in slice" → web channel↔backend split implemented; identity/BSS/Genesys still target.
- **D9** `CLAUDE.md` — "restart removes backend/frontend/voice-agent/Docker Compose" branch note + application-layout paragraph → rebuilt two-service stack.
- **D14** `product-backlog/backlog-index.md` — clarify that epic rows stay `Draft` by product policy while delivery has progressed through Sprint 9 (authoritative delivered state = sprint registry + story/task statuses).

### Out Of Scope

- Rewriting the ~400-line legacy `main` reference section in `development-guide.md`
  (kept as build reference, explicitly disclaimed).
- Any code change, endpoint change, or new diagram (Draw.io/Mermaid) edit.
- Product re-acceptance of epics (a separate Product/Architecture pass).
- The non-documentation findings of the review (endpoint auth, streaming STT-fail
  fallback, OTLP export, latency gate) — those need their own tickets.

### Acceptance Criteria

- No entry document (`README.md`, `CLAUDE.md`, `docs/README.md`,
  `architecture.md`, `adrs/README.md`, `development-guide.md`,
  `operations/backlog.md`, `v1-scope.md`, `channel-identity-boundary.md`) states
  that the backend/frontend/Docker Compose were removed or that only the STT slice
  is built, without immediately clarifying the Sprint 9 rebuilt state.
- The ADR index lists ADR-0032.
- The rebuilt backend contract (port 8080, `/api/conversation/converse` family) is
  documented and the legacy `:8081` / `/ask*` / `/seed` contract is clearly marked
  legacy-`main` reference.
- `git diff --check` passes; all touched docs remain in English.

### Follow-up Tickets Spawned By The Review (not part of this doc task)

- **TASK-BE-019** — authenticate/isolate `/api/knowledge/ingest`, `/sync`,
  `/api/conversation/answer`, `/retrieve` (`product-backlog/tasks/backend-hardening-tasks.md`).
- **TASK-WEB-018** — speak a degraded fallback on streaming STT failure, parity with
  the batch `/turn` 502 (`product-backlog/tasks/web-voice-tasks.md`).
- **TASK-OBS-001** — OTLP exporter / OpenTelemetry spans (backend Tracing→OTel bridge +
  voice OTLP), or record the accepted residual risk in ADR-0028
  (`product-backlog/tasks/observability-tasks.md`).
- **Latency (already tracked):** the ADR-0029 pilot-gate closure is covered by the
  existing **TASK-WEB-015** (perceived-latency optimization levers) + a warm live
  sample — no new ticket created.

---

## TASK-DOC-004 - Truth-in-labeling: mark unimplemented V1 scope as NOT IMPLEMENTED / target

**Parent:** EPIC-012
**Related decisions:** ADR-0003/0004/0005 (BSS/PDF/comparison), ADR-0015 (multi-agent),
ADR-0017 (billing on support foundation), ADR-0019/0020 (escalation/Genesys)
**Depends on:** —
**Classification:** Documentation integrity (product scope honesty)
**Status:** 🚧 In progress (started 2026-08-05, branched from `feat/sprint-11-remote-deployment`)
**Priority:** High
**Branch:** `task/TASK-DOC-004-scope-truth-in-labeling`
**Surfaced by:** Sprint 11 full adversarial code+doc review (2026-08-05,
`docs/architecture/reviews/full-adversarial-review-2026-08-05.md`) — the single
highest-severity finding: product/architecture prose describes billing, multi-agent routing,
escalation and Genesys as present V1 scope, while `backend/src/main` contains **zero**
`BssBilling|InvoicePdf|Galaxion|bill-run` and **zero** `IntentClassifier|AgentProfile|Escalation|Genesys`
(verified by grep).

### Context

A stakeholder reading `docs/product/v1-scope.md` (§Access to BSS Data, §Invoice Comparison) or
`docs/product/cahier-des-charges-fonctionnel.md` (§F3 multi-agent, §5.4 escalation on billing
evidence gaps, §F6/F6bis telephony/WhatsApp) will assume these are delivered. They are not
started. The current runnable product is a **general-support RAG voice bot**. The defect is the
docs over-claiming — the gaps themselves are expected/roadmapped.

### Scope

- Add explicit "NOT IMPLEMENTED — target for a later sprint" markers to the billing/BSS/PDF/
  comparison sections of `v1-scope.md` and the cahier; same for F3 multi-agent routing, §5.4
  escalation, F6/F6bis telephony/WhatsApp, and any Genesys-as-V1 phrasing.
- Add an implementation-status note to ADR-0003/0004/0005/0015/0019/0020 headers (target-only
  vs built), consistent with the ADR README's built-vs-target convention.
- Do **not** rewrite the requirements (they remain the roadmap) — only label current state.

### Acceptance

- Every V1-scope claim not backed by code carries a clear NOT IMPLEMENTED/target marker.
- A reader of the cahier or v1-scope cannot mistake billing/routing/escalation/Genesys as
  delivered. `git diff --check` clean; docs in English.

---

## TASK-DOC-005 - Doc freshness + backlog-index integrity reconciliation

**Parent:** EPIC-012
**Related decisions:** ADR-0036/0037 (status), ADR-0038/0039
**Depends on:** —
**Classification:** Documentation integrity (freshness + backlog)
**Status:** 📋 Open — ready to start
**Priority:** Medium
**Branch:** `task/TASK-DOC-005-freshness-backlog-integrity`
**Surfaced by:** Sprint 11 full adversarial code+doc review (2026-08-05) — multiple
authoritative surfaces still describe a pre-Sprint-7/Sprint-9 state, and `backlog-index.md`
diverges from the source ticket files.

### Context

Stale "Sprint 9 / STT-only / nothing deployed" content persists in `docs/architecture/infra-v1.md`
(L3-6), `docs/README.md` (L3), `docs/architecture/diagrams/README.md`, the architecture-spine
Mermaid diagram (still shows `bridge_server.py`/`agent/bot.py`/`ask*` routes), the sprint-11
"Why now" block, and entry READMEs. ADR-0037 cites the legacy `GET /api/conversation/ask-stream`
(code uses `POST /converse-stream`); ADR-0036/0037 are still "Proposed" though shipped. Backlog
integrity: US-041 (Draft vs Done), US-042 and OQ-008 missing from the index, BUG-001 (Closed vs
New), EPIC-011/012 in the index but not in the epics file.

### Scope

- Refresh the stale banners/diagrams to the Sprint 11 rebuilt stack (or add a dated "current
  state" pointer to `backlog-index.md` where a full rewrite is heavy).
- Fix ADR-0037 endpoint name; promote ADR-0036/0037 to Accepted where code shipped; add the
  ADR-0018→0029 supersession note inline.
- Reconcile `backlog-index.md`: US-041/042, BUG-001 status, OQ-008 row, EPIC-011/012 presence.
- French-in-`docs/` hygiene pass (ADR-0031/0034/0035, some QA reports) — English prose,
  French only where it's genuine test-utterance/example content.

### Acceptance

- No entry/architecture/infra doc still claims the removed-code or STT-only state.
- ADR statuses/endpoints match code; backlog-index matches the source ticket files (no
  orphan/contradiction for the listed IDs). `git diff --check` clean.
