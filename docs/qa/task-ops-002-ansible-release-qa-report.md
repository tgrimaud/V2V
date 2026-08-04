# QA Functional And Latency Report — TASK-OPS-002 (Ansible deploy playbooks + release/rollback runbook)

## Executive Summary

- **Overall readiness:** GO for merge-ready. The Ansible deploy (`deploy/ansible/`)
  and the release runbook (`docs/operations/release-process.md`) satisfy the ticket
  acceptance criteria and the adversarial review. **33/33 deterministic checks pass**
  via `deploy/ansible/qa-validate-ansible.sh` (ansible-core `--syntax-check`,
  inventory topology, real template render with no undefined var, `.env` key parity
  vs the compose `.env.example`, secret hygiene, deploy order, rolling drain, health).
- **Main blockers:** none.
- **Residual risks:**
  1. **Voice draining is best-effort** — the bridge exposes no active-session/`/drain`
     endpoint, so a hard "wait until 0 active calls" is not possible from the outside.
     Mitigated by rolling `serial:1` (VIP peer keeps serving) + an LB node-down hook
     seam + a bounded grace window. Exact drain needs HAProxy node-down (TASK-INFRA-002)
     or a bridge `/drain` endpoint (follow-up). Documented in the runbook and group_vars.
  2. **Live "reaches the tst VMs"** (the three Gherkin scenarios end-to-end) runs only
     against real hosts with SSH + a populated vault, so its live proof is deferred to
     the first tst deploy — same deferral pattern as INFRA-001 (open inputs) and OPS-001.

## Scope Tested

- **Epic / task:** EPIC-012 (Pilot deployment, release & operations) / TASK-OPS-002.
- **Channels:** N/A (deployment tooling; no conversation behavior changed).
- **Providers / fakes:** none — validation is static + a local (`connection=local`)
  template render; no target VM is contacted.
- **Environment:** local, `ansible-core 2.21` in a throwaway venv (`pip install
  ansible-core`). No SSH connection to tst; no vault decrypted.

## Acceptance Scenarios (Gherkin)

```gherkin
Feature: Reproducible deploy, rollback and voice draining

  Scenario: Deploy a version to tst
    Given a published image version and a populated vault
    When the deploy playbook runs against the tst inventory
    Then both tiers run the target version and pass health checks

  Scenario: Rollback
    Given a bad deploy
    When the rollback playbook targets the previous version tag
    Then the previous version is restored and healthy

  Scenario: Drain before voice restart
    Given an active voice call on a bridge being redeployed
    Then the call is drained (not hard-cut) before the container restarts
```

## Test Results (deterministic, offline)

`deploy/ansible/qa-validate-ansible.sh` — **33 passed, 0 failed**:

| Area | Checks | Result |
|------|--------|--------|
| Playbook syntax (`--syntax-check`) | deploy.yml, rollback.yml | PASS |
| Inventory topology | groups redis/backend/voice present, 2 bridges + 2 backends | PASS |
| Template render | backend/voice/redis `.env.j2` render with no undefined var | PASS |
| `.env` key parity | rendered `.env` key set == compose `.env.example` key set (all 3 tiers) | PASS |
| Secret hygiene | vault.yml git-ignored, none tracked, all secret keys from `vault_*`, shared API-key parity, guard rejects `CHANGE_ME` | PASS |
| Reproducibility | deploy + rollback refuse `image_tag=latest`; rollback reuses deploy path | PASS |
| Deploy order + rolling | redis→backend→voice, `serial:1` on both app tiers | PASS |
| Voice draining | drain wired + gated to voice, bounded grace, LB node-down seam | PASS |
| Health | HTTP probe (backend/voice) + Redis `REDISCLI_AUTH` ping (not argv) | PASS |
| KB provisioning | kb_assets wired + gated to backend, copies knowledge-base/ + articles.csv | PASS |

## Scenario Coverage

| Acceptance scenario | Covered? | Evidence |
|---|---|---|
| Deploy a version to tst | Structurally yes; live deferred | `deploy.yml` order + rolling + health gates validated; image_tag guard; template render + key parity prove the rendered `.env` matches the compose contract. Live run needs SSH + vault. |
| Rollback | Structurally yes; live deferred | `rollback.yml` guards a concrete previous tag and imports `deploy.yml` (same order/health), so restore is identical to a deploy at the old tag. |
| Drain before voice restart | Partial (best-effort, documented) | `serial:1` + drain.yml (LB node-down seam + bounded grace) before recreate. Exact "not hard-cut" needs INFRA-002 or a bridge `/drain` endpoint — recorded as residual risk with completion paths. |

## Observability And Latency

- **Runtime-affecting?** No. OPS-002 is deployment tooling (Ansible + docs); it ships
  no application code and changes no conversation/voice runtime path, so no new
  OpenTelemetry traces/metrics/logs are required (per the workflow's
  not-runtime-affecting carve-out).
- Deploy-time visibility comes from Ansible task output + the health gates
  (`/actuator/health`, `GET /`, Redis `PONG`) which fail the play if a tier is unhealthy.

## Security And Privacy

- **Secrets:** only in `group_vars/all/vault.yml` (ansible-vault, git-ignored). `.env`
  rendered `0600` under `no_log`; registry login via `--password-stdin`; Redis auth via
  `REDISCLI_AUTH` (never argv). No secret value is committed (only `CHANGE_ME` templates).
- **Reproducibility guard:** deploy/rollback refuse `latest` and refuse the vault
  placeholder values, so a deploy is always pinned and never silently ships fake secrets.

## Adversarial Review

- **Score:** 93/100 (Pass, ≥90 gate).
- **Blocking findings fixed:** (1) backend deploy did not provision the KB it mounts
  read-only → RAG would stay empty on first deploy; added `kb_assets.yml` (copies
  `knowledge-base/` + `articles.csv`). (2) Redis health ping exposed the password in
  the container argv; switched to `REDISCLI_AUTH`.
- **Accepted residual risk:** best-effort voice draining (completion paths: INFRA-002
  LB node-down or a bridge `/drain` endpoint) and deferred live tst execution.

## Verdict

**GO — merge-ready.** All deterministic checks pass; blocking adversarial findings
fixed; residual risks documented with completion paths. Merge on the user's explicit
request; live deploy/rollback/drain proof runs on the first tst deploy.
