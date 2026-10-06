# TASK-OPS-017 — Raise the post-deploy KB-sync timeout for the bilingual + eir corpus

**Type:** Technical task (deploy config — pilot operations)
**Status:** ✅ **Done on `feat/restart-from-scratch`** (2026-10-06) — `kb_sync_timeout`/`kb_sync_async_seconds`/`kb_sync_poll_retries` raised in `group_vars/backend.yml`; validated against the measured 51-min full sync.
**Priority:** Medium
**Epic:** EPIC-012 (pilot operations / observability hardening)
**Related:** TASK-BE-069 (added the 154-page eir markdown corpus → grew the sync wall time),
TASK-OPS-009/011 (post-deploy sync + skip-when-unchanged), ADR-0030/ADR-0034 (per-article
classification at parse time), ADR-0048 (bilingual corpora).
**Surfaced by:** the `v0.9.5` pilot deploy (2026-10-06) failing its "Wait for the KB sync to finish"
task on a **false client-side timeout**.

## Context

During the `v0.9.5` pilot deploy (TASK-BE-069 rollout), the post-deploy
`POST /api/knowledge/sync` ran a full re-sync of all connectors. The `uri` module's
`timeout: kb_sync_timeout` was **2400 s (40 min)**, but the full sync — bilingual CSV
(~306 EN + ~306 FR, each domain+audience-classified by an embedding call at parse time) **plus**
the 154-page eir markdown corpus — was **measured at ~51 min**:

```
[KB-SYNC] op=syncAll source_type=all processed=769 ingested=154 skipped=527 deleted=88 excluded=88 duration_ms=3085610
```

The HTTP client gave up mid-FR-corpus at 2400 s (`Status code was -1 … Connection failure: timed out`)
while the **backend kept embedding server-side and completed the sync fine**. With
`serial: 1` + `max_fail_percentage: 0` the false timeout aborted the rolling deploy after the
(already healthy) node was recreated, so the second backend node was not upgraded by the same run.

This is purely a client-side wait budget that no longer matches the corpus size; it is not a
backend or data failure.

## Change

In `deploy/ansible/group_vars/backend.yml`, raise the wait budget above the measured 51-min sync:

- `kb_sync_timeout`: 2400 → **3900** (65-min HTTP read; must exceed the whole-sync wall time)
- `kb_sync_async_seconds`: 2700 → **4200** (70-min async job lifetime)
- `kb_sync_poll_retries`: 90 → **140** (140 × 30 s = 70 min of `async_status` polling)
- `kb_sync_poll_delay`: unchanged (30 s)

Comment updated with the measured figure so the budget is traceable.

## Acceptance

- [x] Timeouts raised with headroom above the measured ~51-min full sync.
- [x] Rationale + measured `op=syncAll` figure documented in the var comments.
- [x] No behavior change when a sync is skipped (unchanged sources, TASK-OPS-011) or short.
- [ ] Next full-corpus deploy completes the "Wait for the KB sync" task without a client timeout
      (to confirm on the next `kb_sync_force`/changed-source deploy).

## Notes

- The `v0.9.5` store ended up fully correct despite the aborted play: the sync completed
  server-side (154 eir ingested, 88 internal excluded + deleted), and the second node was
  deployed separately with `kb_sync_after_deploy=false` (shared Postgres already populated).
- A deeper lever (not in this ticket): make the sync incremental/parallel or cache the
  per-article classification so an unchanged re-sync is cheap (ADR-0030 cost dominates).
