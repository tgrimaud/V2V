# Sprint 11 — Remote Deployment & Release Readiness (eir-ai4cc-tst)

## Sprint Objective

Take the two-service web Voice2Voice stack from "runs on a laptop" to "runs on
the **eir-ai4cc-tst** pilot environment with a repeatable release". The platform
team provisioned the first remote environment (Rocky EL9 bare VMs, HAProxy/
Keepalived VIPs, a Postgres pod, and a Redis VM); this sprint packages both
services, wires them to that topology, makes the backend safe to run in two
instances behind a VIP, and stands up the build/deploy pipeline.

Two complementary goals:

1. **Deployable artifacts** — Docker images for the backend and voice bridge,
   docker-compose stacks per tier, and the HAProxy/Keepalived VIP configuration.
2. **Release readiness** — Redis-backed shared conversation memory (so 2 backends
   behind a VIP keep multi-turn context), GitHub Actions CI (test + build/push
   images), and an Ansible/SSH deploy with a documented release/rollback runbook.

This sprint is **off the billing theme**. Billing/identity is intentionally
deferred: per the 2026-08-03 decision, **billing/identity → Sprint 12** and
**telephony/Genesys → Sprint 13**.

## Status

**Status:** 🚧 **In progress** (started 2026-08-03; defined 2026-08-03). Merged into the sprint
branch so far (2026-08-04): **TASK-DEPLOY-001**, **TASK-DEPLOY-002**, **TASK-BE-021**,
**TASK-INFRA-001**, **TASK-OPS-001**, **TASK-OPS-002** and **TASK-BE-022** (all
adversarial + QA passed); integrated `mvn test` **336** green, ArchUnit OK; compose
stacks `qa-validate.sh` 22/22 green; CI workflows `qa-validate-workflows.sh` 22/22
green; Ansible deploy `qa-validate-ansible.sh` 33/33 green. Remaining:
TASK-INFRA-002/003, TASK-DOC-003. Scope locked with
the user: **Docker images + docker-compose on the app VMs**, **GitHub Actions
build/test/image + Ansible/SSH deploy**, **Redis-backed conversation memory**.
Several infrastructure inputs are still open (egress, embeddings placement, TLS,
registry, secrets store, SSH ranges) — captured in
`docs/operations/deployment-eir-ai4cc-tst.md` (Open inputs) and gated behind
TASK-INFRA-003 / TASK-INFRA-002 rather than guessed.

**Sprint branch:** `feat/sprint-11-remote-deployment` (off `feat/restart-from-scratch`).
Two-level branch model (as in Sprint 10): ticket branches fork from and merge
back into this sprint branch (`git merge --no-ff`); the sprint branch merges into
`feat/restart-from-scratch` only at sprint closure, on the user's explicit
request. See `docs/operations/development-workflow.md`.

**Reference docs:** environment inventory
`docs/operations/deployment-eir-ai4cc-tst.md`; decision
`docs/architecture/adrs/ADR-0038-pilot-deployment-architecture-eir-ai4cc-tst.md`;
generic target `docs/architecture/infra-v1.md`; ticket details
`tasks/deployment-tasks.md`.

## Roadmap Context

| Sprint | Theme | State |
|---|---|---|
| Sprint 9 | Hardening / assainissement | ✅ Done (2026-07-28) |
| Sprint 10 | Pilot-readiness latency & perceived latency | ✅ Done (closed 2026-07-31) |
| **Sprint 11** | **Remote deployment & release readiness (eir-ai4cc-tst)** | 🚧 Planned (defined 2026-08-03) |
| Sprint 12 (tentative) | Customer identity + BSS/PDF evidence + deterministic comparison (EPIC-002/003/004) | Planned — gated by OQ-001/003/004 |
| Sprint 13 (tentative) | Telephony channel (US-018) + Genesys advisor handoff (EPIC-007) | Planned — gated by OQ-006 |

## Why now (state that justifies the sprint)

- The pilot needs a **real environment**. The platform team has provisioned
  eir-ai4cc-tst; the stack currently has **no Dockerfile, no CI, and binds
  `127.0.0.1`** — none of it deploys as-is.
- The environment runs **two backend instances behind a VIP**, but conversation
  memory is **in-process** today: consecutive turns can land on different
  instances and lose history. Redis-backed memory (ADR-0008) is a hard
  prerequisite, not a nice-to-have.
- Sprint 10 validated **perceived latency** on a responsive loop; running that
  loop on tst is the natural next step **before** adding billing logic, so the
  billing sprint is validated on an already-deployed, already-responsive pilot.
- A reproducible **build/release process** (versioned images, tag-based rollback)
  is the entry ticket to the ADR-0010 industrialization path; doing it now avoids
  hand-deploying every future sprint.

## Tickets

| Ticket | Title | Role | Status |
|---|---|---|---|
| TASK-DEPLOY-001 | Backend Java Docker image (multi-stage JDK17→JRE17, non-root, `HEALTHCHECK /actuator/health`, env-driven) | Package | ✅ **Merged into sprint-11** (2026-08-04, `--no-ff` `ee42541`) — image build-validated (non-root, Java 17, boots Spring Boot) |
| TASK-DEPLOY-002 | Voice bridge Python Docker image (heavy deps `pipecat`/`aiortc`/`opencv`, `--host 0.0.0.0`, healthcheck `/`, non-root) | Package | ✅ **Merged into sprint-11** (2026-08-04, `--no-ff` `579fcc9`) — image build + runtime smoke validated (binds `0.0.0.0:8090`, `GET /` 200, non-root) |
| TASK-BE-021 | Redis-backed conversation memory (`RedisConversationMemoryAdapter`, `CONVERSATION_STORE=redis`) so the 2 backends behind VIP `.11` share session state — activates ADR-0008 | Enable (backend) | ✅ **Merged into sprint-11** (2026-08-04, `--no-ff` `daa2102`; adversarial 92/100 → QA GO) — integrated `mvn test` **336** green, ArchUnit OK; default `memory` unchanged; blocking fix: Actuator Redis health indicator gated `REDIS_HEALTH_ENABLED` (default off) so `/actuator/health` stays UP in memory mode (live-verified); [QA report](../../docs/qa/sprint-11-deployment-qa-report.md) |
| TASK-BE-022 | Constant-time api-key gate unification (`ApiKeyGuard`) + client-controlled log/header sanitization (`correlation_id`/`channel`) — 2026-08-04 backend adversarial-review findings #1 & #3 | Enable (backend, hardening) | ✅ **Merged into sprint-11** (2026-08-04, `--no-ff` `3dafffd`; adversarial 95/100 → QA GO) — `/converse`+`/converse-stream` delegate to constant-time `ApiKeyGuard`; `CorrelationId.sanitize` strips control chars + caps 200 on every client id/channel before MDC/log/header; [QA report](../../docs/qa/task-be-022-auth-log-hardening-qa-report.md). Spawned TASK-BE-023 (ops-surface gating, deferred) |
| TASK-INFRA-001 | docker-compose deploy stacks + `.env` templates per tier (backend→Postgres `.102`/Redis `.107`/embeddings/Mistral; voice→backend VIP `.11`/Gradium; Redis stack) | Wire | 🚧 Implemented (2026-08-04) on `task/TASK-INFRA-001-compose-stacks` — 3 stacks + `.env.example` + README, all pass `docker compose config`; ✅ **Merged into sprint-11** (2026-08-04, `--no-ff` `9fef902`; adversarial 93/100 + QA GO 22/22, [report](../../docs/qa/task-infra-001-compose-stacks-qa-report.md); blocking KB volume-mount fix applied) |
| TASK-INFRA-002 | HAProxy + Keepalived config for the two VIPs (voice `.10`→t01/t02 TLS edge, backend `.11`→t03/t04), health checks, finalized ports, VRRP failover — coordinated with the platform team | Wire (infra) | To do |
| TASK-INFRA-003 | Decision + spike: embeddings placement (Ollama CPU co-located vs Mistral embeddings → 1024-dim recreation) and provider egress (Mistral/Gradium/registry) → ADR addendum | Decide | To do (gated by open inputs) |
| TASK-OPS-001 | GitHub Actions CI: `mvn test` + voice-agent `unittest`/`behave`, build & push both images to the registry, version/tag scheme | CI | 🚧 Implemented (2026-08-04) on `task/TASK-OPS-001-github-actions-ci` — `ci.yml` test gate + `images.yml` build/push to GHCR (reusable `tests.yml` gates both); ✅ **Merged into sprint-11** (2026-08-04, `--no-ff` `1e431f2`; adversarial 93/100 + QA GO 22/22, [report](../../docs/qa/task-ops-001-github-actions-ci-qa-report.md); reusable `tests.yml` gates `images.yml`) |
| TASK-OPS-002 | Ansible deploy playbooks + release/rollback runbook (`docs/operations/release-process.md`): render `.env` from secrets, `docker compose up`, voice **session draining**, tag-based rollback | Release | ✅ **Merged into sprint-11** (2026-08-04, `--no-ff` `20f1770`; adversarial 93/100 + QA GO 33/33, [report](../../docs/qa/task-ops-002-ansible-release-qa-report.md)) |
| TASK-DOC-003 | Keep deployment docs in sync as tickets land + author the operational first-deploy runbook (checklist, DB `CREATE EXTENSION vector`, smoke test) | Docs | To do |

Full ticket details live in `tasks/deployment-tasks.md`.

## Open inputs (collected incrementally)

Blocking or shaping the tickets — full list in
`docs/operations/deployment-eir-ai4cc-tst.md` (Open inputs needed):

1. Ingress flows to authorize (SSH source ranges, who reaches voice VIP `.10`, confirmed VIP ports).
2. Internet egress from tst (Mistral, Gradium, container registry — direct/proxy).
3. Embeddings placement decision (drives TASK-INFRA-003).
4. TLS certificate + FQDN for the voice VIP (`.prod.lan` / `10.195.59.39`).
5. Container registry reachable from the VMs (GHCR vs internal Nexus/Artifactory) + credentials.
6. Secrets store + delivery (GitHub secrets → Ansible vault → `.env`).
7. Postgres DB name/user/password on `.102` + `vector` extension confirmation.

## Out Of Scope

- Billing/identity, BSS/PDF evidence and deterministic comparison (Sprint 12,
  gated by OQ-001/003/004).
- Telephony and Genesys handoff (Sprint 13, gated by OQ-006).
- A full OTLP observability stack: the inventory has **no collector host**, so
  OTLP export stays opt-in and off by default (ADR-0028/ADR-0038); keep structured
  logs + `/actuator/metrics`. A collector deployment is a later observability ticket.
- Kubernetes: `infra-v1.md` is the long-term operator target; this pilot is bare
  VMs + HAProxy (ADR-0038).
- Any change to what the bot *says* — this sprint changes *where* it runs, not the
  answer content (DEC-002 stays enforced).

## Exit Criteria

- Both services build into reproducible non-root images that pass their
  healthchecks with a fully env-driven configuration (TASK-DEPLOY-001/002).
- With `CONVERSATION_STORE=redis`, a multi-turn conversation keeps its context
  across the two backend instances behind VIP `.11`; the in-memory default and
  existing tests are unchanged (TASK-BE-021).
- The docker-compose stacks bring up each tier on the tst VMs, wired to Postgres,
  Redis and the cloud providers; the VIPs load-balance and fail over with working
  health checks (TASK-INFRA-001/002).
- The embeddings placement + egress decision is made and recorded (ADR addendum),
  and a KB sync + retrieval works on tst with no dimension mismatch (TASK-INFRA-003).
- GitHub Actions runs the test gates on PRs and publishes tagged images on a
  release; Ansible deploys a version to tst and can roll back to the previous tag,
  draining voice sessions before restart (TASK-OPS-001/002).
- A delivery engineer can follow `docs/operations/release-process.md` +
  `deployment-eir-ai4cc-tst.md` to reach a passing end-to-end voice smoke test on
  tst without tribal knowledge (TASK-DOC-003).
- Each ticket passes adversarial review ≥ 90% then QA before the branch is
  merge-ready. Merge only on the user's explicit request.
