# Adversarial Review — TASK-OPS-011 (skip post-deploy KB sync when unchanged)

Reviewed with the `adversarial-code-review` skill. Scope: the Ansible deploy change that skips the
post-deploy `POST /api/knowledge/sync` when no mounted KB source changed.

## Verdict

Proceed. Small, well-contained deploy-only change; live-validated on the pilot (sync skipped, all six
hosts green in ~4 min). One documented operational residual.

## Satisfaction Score

Score: 93/100
QA gate: Pass

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|
| — | None | — | — |

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|
| Medium (residual, documented) | A manual `DELETE FROM vector_store` (or data loss) **without** a KB-source change and **without** `kb_sync_force=true` would be skipped → RAG left empty, and the retrieval smoke (HTTP-200-only by design, ADR-0034) would not fail the deploy. | `kb_sync.yml` gate; smoke asserts 200 only | Documented mitigation: run with `-e kb_sync_force=true` after any manual store change (noted in `group_vars/backend.yml` + `release-process.md`). Pre-existing smoke property, not introduced here. |
| Low | `ansible.builtin.copy` reports `changed` on metadata-only diffs (mode/owner), which would trigger an (unnecessary but safe) full sync. | copy semantics | Accept — fail-safe direction (extra sync, never a missed one). Files are fixed-mode `0644`, so this is unlikely. |
| Info | `kb_assets_changed` is a per-host fact; the sync is `run_once` on the first backend node, so that node's result governs. KB sources are identical across nodes (same repo), so consistent. | `kb_assets.yml` set_fact; `run_once` | Fine. |
| Info | Added `quiet: true` to the processed-count assert to reduce log noise on the (now rarer) sync path. | `kb_sync.yml` assert | Cosmetic. |

## Story Coverage

| Acceptance | Covered? | Evidence |
|---|---|---|
| Syntax-check passes | Yes | `ansible-playbook deploy.yml --syntax-check` → ok |
| Unchanged KB → sync skipped, all tiers complete fast | Yes | live re-deploy: both backends "KB sync SKIPPED (kb_assets_changed=false)"; `PLAY RECAP` 6 hosts, 0 failed, ~4 min; `vector_store`=10,168 kept |
| Force / changed-source still syncs | Logic-verified | gate `kb_sync_required = kb_assets_changed or kb_sync_force`; not force-run live (would cost the 40 min pass) |

## Test Evidence

- Live validation on eir-ai4cc-tst (not a stub): `/tmp/deploy_094c.log` — skip debug on t03+t04, no
  `Trigger/Wait` sync execution, clean recall across redis + both backends + both voice bridges.
- `--syntax-check` clean. `ansible-lint` not installed on the control node (not run).
- Fresh-host path reasoned (copies create files → `changed` → sync runs); not re-provisioned live.

## Observability

- The skip is explicit and auditable: a `debug` line states the host, the reason
  (`kb_assets_changed=false`) and the `kb_sync_force` override. The warm-up readiness gate (BUG-021)
  and the read-only retrieval smoke still run every deploy, so pipeline health is still probed.

## Security / Privacy

- No secrets exposed: `no_log` preserved on the key-slurp, key-extract, warm-up and sync-trigger
  tasks. The new debug carries only the inventory hostname. No new network surface, no new creds.

## Required Developer Actions

1. None blocking.
2. Operator note (documented): use `kb_sync_force=true` after any manual `vector_store` change.

## Residual Risk If Accepted

- A silent empty-RAG state is possible only via a manual store wipe without a KB change and without
  the force flag; mitigated by documentation and the `kb_sync_force` knob. Fail-safe otherwise (the
  change can only *skip a redundant* sync, never drop a needed one on a real KB change / fresh host).
