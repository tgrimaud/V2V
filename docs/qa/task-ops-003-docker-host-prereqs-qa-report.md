# QA Report — TASK-OPS-003 (Ansible host prerequisites: Docker + compose on Rocky EL9)

## Executive Summary

- **Readiness:** GO for merge-ready. A new idempotent `host_prereqs` role + `prereqs.yml`
  provision the container runtime (Docker Engine + compose v2 plugin + buildx) on the
  bare Rocky EL9 VMs, enable the service, add the deploy user to the `docker` group,
  and open each tier's published port in firewalld when active. This removes the
  first-deploy blocker (the `compose_tier` role assumed Docker already existed).
- **Deterministic validation:** `prereqs.yml` syntax-check PASS; `qa-validate-prereqs.sh`
  **21/21**; OPS-002 `qa-validate-ansible.sh` still **33/33** (no regression).
- **Blockers:** none.
- **Residual (accepted):** tier port opened in the default firewalld zone (Redis 6379
  with auth on; source-restrict = hardening follow-up); SELinux `:Z` relabel of the KB
  `:ro` mount documented, applied only if the first deploy hits an AVC denial; **live
  run on a real Rocky EL9 VM deferred** (VMs unreachable from CI — network open input #1).

## Scope Tested

- **Task:** EPIC-012 / TASK-OPS-003 (host provisioning).
- **Environment:** local; `ansible-core 2.21`, syntax-check + structural QA. No VM contacted.

## Acceptance Scenario (Gherkin)

```gherkin
Scenario: A bare Rocky EL9 VM is ready to run compose stacks
  Given a fresh redis/backend/voice VM with SSH access
  When prereqs.yml runs against it
  Then docker + the compose v2 plugin are installed and the service is enabled
  And re-running prereqs.yml reports no changes (idempotent)
```

## Coverage

| Acceptance element | Covered? | Evidence |
|---|---|---|
| Docker + compose v2 installed | Structurally yes; live deferred | `host_prereqs` installs docker-ce/-cli, containerd.io, buildx + compose plugins from the Docker CE repo; verify task runs `docker compose version`. |
| Service enabled | Yes | `systemd: name=docker enabled=true state=started`. |
| Idempotent re-run | By design | dnf/get_url/systemd modules are idempotent; firewalld add treats `ALREADY_ENABLED` as no-change. |
| Targets the right hosts | Yes | `prereqs.yml hosts: redis:backend:voice`; excludes platform-managed data/lb. |

## Deterministic Checks

| Check | Result |
|-------|--------|
| `ansible-playbook prereqs.yml --syntax-check` | PASS |
| `qa-validate-prereqs.sh` (targets, repo, packages, service, docker group, firewalld guard, per-tier port, conflict handling, verify) | 21/21 PASS |
| OPS-002 `qa-validate-ansible.sh` (no regression) | 33/33 PASS |
| `git diff --check` | clean |

## Adversarial Review

- **Score:** 92/100 (Pass, ≥90 gate).
- **Blocking finding fixed:** on Rocky EL9 `containerd.io` (docker-ce) conflicts with the
  `runc` shipped by the default container-tools (podman) → `dnf install` would fail.
  Added `allowerasing: true` so dnf removes the conflicting packages on the app VMs
  (the DB VM's podman pod on `.102` is not a prereqs target).
- **Accepted residual:** firewalld port opened in the default zone (Redis auth on);
  SELinux `:Z` documented; docker-group membership needs a new session (irrelevant to
  the root-become automation); live run deferred pending VM network access.

## Verdict

**GO — merge-ready.** The container-runtime gap before the first deploy is closed;
deterministic checks green with no OPS-002 regression. Merge on the user's explicit
request; the live idempotency proof runs on the first reachable Rocky EL9 VM.
