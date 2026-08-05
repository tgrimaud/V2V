# QA report — TASK-DOC-003 (deployment docs sync + first-deploy runbook)

**Ticket:** TASK-DOC-003 — Deployment documentation sync + operational runbook
**Branch:** `task/TASK-DOC-003-deployment-docs`
**Date:** 2026-08-05
**Classification:** V1 pilot deployment (docs). **Not runtime-affecting** (docs +
Ansible comment/fail-message strings only; no task logic changed).
**Adversarial doc review:** 93/100 (Pass) — accuracy verified against code/config.
**Verdict:** ✅ GO (merge-ready). Live tst run of the runbook deferred to network
access (open input #1).

## Scope validated

- New `docs/operations/first-deploy-runbook.md` (zero-to-running chronological
  runbook + smoke test + rollback + first-deploy troubleshooting).
- Image-tag accuracy fix (git tag `vX.Y.Z` → image tag `X.Y.Z`, no `v`) across
  `release-process.md`, `deploy/ansible/README.md`, `group_vars/all/vars.yml`,
  `deploy.yml` + `rollback.yml` header/fail-msg, and open input #5 in
  `deployment-eir-ai4cc-tst.md`.
- Cross-links from `docs/README.md`, `deployment-eir-ai4cc-tst.md`,
  `release-process.md`, `infra-v1.md`, `development-workflow.md`.

## Acceptance criterion

```gherkin
Scenario: Runbook is executable
  Given a clean tst environment and the runbook
  When a delivery engineer follows it
  Then they reach a passing end-to-end voice smoke test without tribal knowledge
```

**Status:** Structurally satisfied — the runbook covers access, image publish,
vault, host provisioning, Postgres bootstrap, tiered deploy, LB/TLS, smoke and
rollback with copy-pasteable commands. Full end-to-end execution on tst is
**deferred to network access** (open input #1); tier-B voice turn also needs the
TLS edge (#4) and STUN/TURN (#1). Tier-A backend/RAG smoke is executable as soon as
the tiers are up.

## Deterministic checks (all green)

| # | Check | Result |
|---|-------|--------|
| 1 | `git diff --check` (whitespace/conflict) | clean |
| 2 | All runbook relative links resolve to real files/dirs | 9/9 OK |
| 3 | Backend health endpoint `GET /api/health` exists | ✓ `HealthController` `@RequestMapping("/api")` + `/health` |
| 4 | Conversation smoke `POST /api/conversation/converse` exists | ✓ `ConverseController` |
| 5 | RAG sync `POST /api/knowledge/sync` exists | ✓ `KnowledgeController` |
| 6 | Smoke body uses snake_case (`conversation_id`, `correlation_id`) | ✓ `JacksonConfig` = `SNAKE_CASE` |
| 7 | `x-api-key` gate + 401 on mismatch documented correctly | ✓ `ConverseController.apiKeyGuard` |
| 8 | Redis verify uses real container name `voice-support-redis` | ✓ `deploy/compose/redis` `container_name` |
| 9 | Voice health `GET :8090/ → 200` matches compose healthcheck | ✓ `deploy/compose/voice` healthcheck |
| 10 | KB assets path (`knowledge-base/` + `articles.csv`, `:ro`) | ✓ `deploy/compose/backend` `KB_HOST_PATH` bind |
| 11 | Ollama model pull backend-gated (`nomic-embed-text`) | ✓ `roles/compose_tier/tasks/ollama_model.yml` |
| 12 | VM IPs match inventory (.102 pg, .103/.104 voice, .105/.106 be, .107 redis, .10/.11 VIPs) | ✓ deployment doc inventory |
| 13 | Image tag `0.4.0` (no `v`) really published + pullable | ✓ `imagetools inspect` OK (`0.4.0`, `latest`); `v0.4.0` not found |
| 14 | No residual `image_tag=v…` example left in docs/deploy | ✓ swept (deploy.yml/rollback.yml headers + fail-msg fixed) |
| 15 | `deploy.yml` / `rollback.yml` still refuse `latest` after edits | ✓ `--syntax-check` OK, OPS-002 QA 33/33 |

## Regression

- OPS-002 Ansible QA: **33/33** after the comment/fail-msg edits.
- OPS-003 prereqs QA: **21/21** (unchanged).
- Compose QA: **22/22** (unchanged).

## Blocking findings

None.

## Residual risk (accepted)

- The runbook has not been executed end-to-end on tst (no network route to
  `192.168.0.0/24` yet — open input #1). Commands are verified against the code
  and config, not a live run. The tier-B voice turn additionally depends on the
  TLS edge (#4) and STUN/TURN (#1).
