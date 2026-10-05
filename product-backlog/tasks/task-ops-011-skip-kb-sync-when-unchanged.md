# TASK-OPS-011 — Skip the post-deploy KB sync when no KB source changed

**Type:** Ops / deploy task · **Status:** ✅ Merged into `feat/restart-from-scratch` (2026-10-05, `--no-ff` `c5cff48`); branch deleted. Live-validated on pilot (sync skipped, all tiers green). Adversarial review 93/100 (Pass, `docs/qa/task-ops-011-adversarial-review.md`).
**Branch:** `task/TASK-OPS-011-skip-kb-sync-when-unchanged` (off `feat/restart-from-scratch`)
**Related:** TASK-OPS-009 (post-deploy KB sync), ADR-0048 (CSV corpus), ADR-0030 (domain classification at parse), TASK-INFRA-011 (deploy health gate), v0.9.4 deploy

## Context

The post-deploy step `kb_sync.yml` fires `POST /api/knowledge/sync` on the backend tier after every
deploy. It is storage-idempotent (content-hash upsert skip), **but** per ADR-0030 every article is
also domain-classified by a CPU-Ollama embedding call **at parse time on every sync**, so even an
*unchanged* corpus is fully re-classified. On the pilot this full pass runs **> 40 min** and, during
the **v0.9.4** deploy, exceeded the sync's 2400 s (40 min) inner HTTP timeout. Under
`serial:1`/`max_fail_percentage:0` that aborted the whole rolling deploy after the first backend node
(backend `t04` and the voice tier never upgraded); the deploy had to be re-run with
`-e kb_sync_after_deploy=false` to finish. A code-only release (unchanged KB) should not pay — or be
blocked by — a full re-embedding pass.

## Change (Ansible deploy only — not runtime-affecting)

- `roles/compose_tier/tasks/kb_assets.yml`: register the three `ansible.builtin.copy` tasks
  (markdown dir, primary CSV, optional FR CSV) and set `kb_assets_changed` from their `is changed`
  results. `copy` compares content checksums, so this is an exact "a KB source differs from what's on
  the host" signal; a fresh host reports changed (files created) so the first sync still runs.
- `roles/compose_tier/tasks/kb_sync.yml`: compute `kb_sync_required = kb_assets_changed or
  kb_sync_force`. Gate the four heavy tasks (trigger / wait / report / assert) on it; emit a clear
  "KB sync SKIPPED (sources unchanged)" debug otherwise. The BUG-021 warm-up readiness gate and the
  read-only retrieval smoke still run every deploy, so the pipeline is verified either way.
- `group_vars/backend.yml`: add documented knob `kb_sync_force: false`; correct the stale "idempotent
  re-deploys finish in seconds" comment.
- `roles/compose_tier/tasks/main.yml`: comment updated to document the TASK-OPS-011 skip.
- `docs/operations/release-process.md`: document the change-detection skip + `kb_sync_force`.

## Acceptance

- [x] `ansible-playbook deploy.yml --syntax-check` passes.
- [x] Re-deploying `0.9.4` with **no KB change** skips the sync on the backend tier (both nodes logged
      "KB sync SKIPPED … kb_assets_changed=false"), completes **all** tiers (backend t03/t04 + voice
      t01/t02 + redis) in ~4 min (`PLAY RECAP` 0 failed / 0 unreachable) without the 40 min wait, and
      keeps the existing `vector_store` populated (10,168 chunks).
- [x] `-e kb_sync_force=true` still runs a full sync; a changed KB source still triggers a sync —
      gate is `kb_sync_required = kb_assets_changed or kb_sync_force` (logic-verified; not force-run
      live to avoid the 40 min pass).
- [ ] Adversarial review ≥ 90% (persisted to `docs/qa/`), then QA/user validation. No merge without
      explicit user request.

## Notes

- Complementary (not required by this ticket): a backend change could cache the domain classification
  by content hash so a genuine re-sync is also fast; tracked separately if pursued.
