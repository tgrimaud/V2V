# BUG-009 — Ansible deploy aborts on non-voice tiers: `'item' is undefined`

## Header

- **Bug ID:** BUG-009
- **Title:** `compose_tier` "Re-enable the voice bridge in the load balancer" task templates `delegate_to: "{{ item }}"` on every tier → redis/backend deploy aborts with `'item' is undefined`
- **Status:** Ready for adversarial review
- **Severity:** High
- **Priority:** P1
- **Detected by:** User validation (first pilot deploy)
- **Detected date:** 2026-08-14
- **Related user story:** TASK-OPS-002 (Ansible deploy) / TASK-INFRA-007 (LB drain/re-enable hook)
- **Related epic:** EPIC-012 (V1 pilot deployment)
- **Branch:** fixed inline on `feat/sprint-11-remote-deployment` (found during deploy; no dedicated `fix/` branch)
- **Owner:** Cross-functional (infra / deploy)

## Problem Statement

Running `ansible-playbook deploy.yml` aborts the whole run on the **redis** (and would on the **backend**) tier at the final task "Re-enable the voice bridge in the load balancer" with `Task failed: 'item' is undefined`, even though that task is meant to run only on the voice tier.

## Environment

- **Environment:** pilot (eir-ai4cc-tst); reproduces anywhere the playbook targets a non-voice tier
- **Channel:** backend-only (deploy tooling)
- **Build or commit:** `deploy/ansible/roles/compose_tier/tasks/main.yml` as of `5e1e4c8`
- **Provider configuration:** ansible-core 2.21.3, `podman compose`

## Reproduction Steps

1. Given the `compose_tier` role is applied to a non-voice tier (`redis` or `backend`), where `voice_lb_socket_hosts` is undefined.
2. When the play reaches the inline task `Re-enable the voice bridge in the load balancer` (`delegate_to: "{{ item }}"` + `loop: "{{ voice_lb_socket_hosts }}"`, gated by `when: tier == 'voice'`).
3. Then Ansible templates `delegate_to`/the loop while building the task, before `when` short-circuits, and fails with `'item' is undefined` → the play aborts (`failed=1`), so the following backend and voice plays never run.

## Expected Result

The re-enable step is a voice-only, best-effort hook (`ignore_unreachable` + `failed_when: false`) and must be a no-op on redis/backend without aborting the deploy.

## Actual Result

`fatal: [vlb-ai4cc-t02.prod.lan -> {{ item }}]: FAILED! => "Task failed: 'item' is undefined"`; `PLAY RECAP … failed=1`; backend/voice tiers not deployed. `failed_when: false` cannot catch it because it is a task-build-time templating error, not a task result.

## Evidence

- Origin: `deploy/ansible/roles/compose_tier/tasks/main.yml:96` (`delegate_to: "{{ item }}"`), `:99`.
- `NO MORE HOSTS LEFT` after the redis play; only `localhost` + `vlb-ai4cc-t02` in the recap.
- Contrast: the sibling drain step never fails on non-voice tiers because it is an `include_tasks: drain.yml` gated `when: tier == 'voice'` (never constructed off the voice tier).

## Impact

- **Operational / pilot-readiness:** a first deploy cannot complete — redis "succeeds" then the run aborts, backend + voice never deploy. Hard blocker for any `deploy.yml` run that includes a non-voice tier.
- No customer data / security impact.

## Acceptance Criteria For Fix

- [x] The defect no longer reproduces (full `deploy.yml` completes redis→backend→voice).
- [ ] A regression test / lint covers the failure (e.g. `deploy/ansible/qa-validate-ansible.sh` asserts no inline `delegate_to: "{{ item }}"` outside a voice-gated include).
- [x] OpenTelemetry: not applicable (deploy tooling, no app runtime change).
- [ ] Adversarial code review ≥ 90%.
- [ ] QA retest passes.
- [x] Documentation/backlog updated (this ticket + inline rationale comment).

## Developer Notes

- **root cause:** an inline task with `loop` + `delegate_to: "{{ item }}"` is built on every tier; Ansible templates `delegate_to` before `when` short-circuits, and `item` is unbound off the voice tier (where `voice_lb_socket_hosts` is undefined).
- **files changed:** `deploy/ansible/roles/compose_tier/tasks/main.yml` (inline task → `include_tasks: lb_reenable.yml` gated `when: tier == 'voice'`); new `deploy/ansible/roles/compose_tier/tasks/lb_reenable.yml` holding the delegated loop (mirrors `drain.yml`).
- **tests added/updated:** none yet (see AC).
- **OpenTelemetry added/updated:** n/a.
- **residual risk:** low; verified live — full deploy completed and the included re-enable correctly skips (empty `voice_lb_socket_hosts`).

## QA Retest

- **Retested by:** (pending)
- **Retest date:** —
- **Scenarios rerun:** full `deploy.yml -e image_tag=0.5.0` on the pilot completed redis→backend→voice (`failed=0` all tiers).
- **Result:** Passed (live, informal) — formal QA retest pending.
- **Retest evidence:** pilot deploy 2026-08-14, all tiers healthy.

## Closure

- **Closed by:** —
- **Closed date:** —
- **Closure reason:** —
