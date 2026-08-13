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
green; Ansible deploy `qa-validate-ansible.sh` 33/33 green; HAProxy/Keepalived
`qa-validate-haproxy.sh` 25/25 green (incl. real `haproxy -c`). TASK-INFRA-003
(ADR-0039 embeddings decision) and TASK-OPS-003 (Docker host prereqs) merged into
sprint-11 (2026-08-05); prereqs `qa-validate-prereqs.sh` 21/21 green. TASK-DOC-003
(first-deploy runbook + image-tag accuracy) is merge-ready. All Sprint 11 tickets are
now implemented; live tst deploy is gated only by network access (open input #1). Scope locked with
the user: **Docker images + docker-compose on the app VMs**, **GitHub Actions
build/test/image + Ansible/SSH deploy**, **Redis-backed conversation memory**.
Several infrastructure inputs are still open (egress, embeddings placement, TLS,
registry, secrets store, SSH ranges) — captured in
`docs/operations/deployment-eir-ai4cc-tst.md` (Open inputs) and gated behind
TASK-INFRA-003 / TASK-INFRA-002 rather than guessed.

**Scope extended (2026-08-05):** after the original tickets landed, a **full
adversarial review of the whole application** (code + docs) was run and persisted
(`docs/architecture/reviews/full-adversarial-review-2026-08-05.md`, verdict *proceed
with conditions*, overall ≈2.6/5). Its follow-up tickets are folded into this sprint
(see **Full adversarial review follow-ups** below). This includes the hardening
tickets already merged during the review loop (**BUG-006**, **TASK-BE-024**,
**TASK-OPS-004**, **TASK-INFRA-004**) plus the newly-opened must/should-fix set;
the deferred tickets are tracked but out of this sprint's execution. **TASK-DOC-004**
(truth-in-labeling of unimplemented V1 scope) is the first to be started.

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

> **Note (2026-08-05):** this block describes the **pre-sprint** state that justified
> Sprint 11. Most gaps below are now closed — Docker images, CI, `deploy/compose/`
> stacks, HAProxy/Keepalived, Ansible deploy and Redis-backed memory are delivered on
> the sprint branch; live go-live remains gated by network-access open inputs
> (TASK-INFRA-006). Read the **Status** block above for current state.

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
| TASK-INFRA-002 | HAProxy + Keepalived config for the two VIPs (voice `.10`→t01/t02 TLS edge, backend `.11`→t03/t04), health checks, finalized ports, VRRP failover — coordinated with the platform team | Wire (infra) | ✅ **Merged into sprint-11** (2026-08-04, `--no-ff` `f2cc838`; adversarial 92/100 + QA GO 25/25 incl. real `haproxy -c`, [report](../../docs/qa/task-infra-002-haproxy-vips-qa-report.md)) |
| TASK-INFRA-003 | Decision + spike: embeddings placement (Ollama CPU co-located vs Mistral embeddings → 1024-dim recreation) and provider egress (Mistral/Gradium/registry) → ADR addendum | Decide | ✅ Implemented — **ADR-0039** (Ollama CPU sidecar per backend VM; Mistral embeddings rejected); ✅ adversarial 92/100 (Pass); ✅ QA GO (compose config + Ansible 33/33 + compose 22/22, [report](../../docs/qa/task-infra-003-embeddings-egress-qa-report.md)); ✅ **Merged into sprint-11** (2026-08-05, `--no-ff` `be37843`) |
| TASK-OPS-001 | GitHub Actions CI: `mvn test` + voice-agent `unittest`/`behave`, build & push both images to the registry, version/tag scheme | CI | 🚧 Implemented (2026-08-04) on `task/TASK-OPS-001-github-actions-ci` — `ci.yml` test gate + `images.yml` build/push to GHCR (reusable `tests.yml` gates both); ✅ **Merged into sprint-11** (2026-08-04, `--no-ff` `1e431f2`; adversarial 93/100 + QA GO 22/22, [report](../../docs/qa/task-ops-001-github-actions-ci-qa-report.md); reusable `tests.yml` gates `images.yml`) |
| TASK-OPS-002 | Ansible deploy playbooks + release/rollback runbook (`docs/operations/release-process.md`): render `.env` from secrets, `docker compose up`, voice **session draining**, tag-based rollback | Release | ✅ **Merged into sprint-11** (2026-08-04, `--no-ff` `20f1770`; adversarial 93/100 + QA GO 33/33, [report](../../docs/qa/task-ops-002-ansible-release-qa-report.md)) |
| TASK-OPS-003 | Ansible host prerequisites: install Docker Engine + compose v2 plugin (Rocky EL9) + tier-aware firewalld, before deploy (the compose_tier role assumes Docker exists) | Provision | ✅ Implemented — `host_prereqs` role + `prereqs.yml`; adversarial 92/100 (Pass; podman/runc conflict fixed); QA GO 21/21 + OPS-002 33/33 ([report](../../docs/qa/task-ops-003-docker-host-prereqs-qa-report.md)); ✅ **Merged into sprint-11** (2026-08-05, `--no-ff` `a1dacab`; live run deferred, #1) |
| TASK-DOC-003 | Keep deployment docs in sync as tickets land + author the operational first-deploy runbook (checklist, DB `CREATE EXTENSION vector`, smoke test) | Docs | ✅ Implemented — new `docs/operations/first-deploy-runbook.md` (zero-to-running) + image-tag accuracy fix (git `vX.Y.Z` → image `X.Y.Z`); adversarial 93/100 (Pass); QA GO 15/15 + OPS-002 33/33 regression ([report](../../docs/qa/task-doc-003-deployment-docs-qa-report.md)); ✅ merge-ready (live run deferred, #1) |
| TASK-INFRA-008 | Adapt the deploy to the **podman** runtime (Option B) — VMs run podman 5.8.2 + `podman-docker` shim, no Docker CE / no compose provider, SELinux Enforcing | Provision (runtime alignment) | ✅ Implemented (2026-08-13) — `host_prereqs` drops Docker CE, installs the Compose v2 binary as podman's **compose provider** (+ `containers.conf`/`nodocker`, rootful `podman.socket`); `compose_cmd → "podman compose"`; `compose_tier` login via `podman`; backend KB mount `:ro → :ro,Z`. Surfaced by Step 0 access; ADR-0038 addendum (2026-08-13); live validation folded into tier-A smoke |

Full ticket details live in `tasks/deployment-tasks.md`.

## Full adversarial review follow-ups (added 2026-08-05)

Surfaced by the whole-application adversarial review
(`docs/architecture/reviews/full-adversarial-review-2026-08-05.md`). Already-merged
hardening tickets are listed for accuracy; the must/should-fix set is **in this
sprint's scope**; the deferred set is tracked but **out of execution** this sprint.

### Already merged during the review loop

| Ticket | Title | Status |
|---|---|---|
| BUG-006 | VRRP fails over on HAProxy death (keepalived weight -60) | ✅ Merged (`7b1ba56`) — live retest pending |
| TASK-BE-024 | Sanitize `conversation_id` in memory logs + pipeline Redis append | ✅ Merged (`174af74`) |
| TASK-OPS-004 | Source-scoped firewalld, provisioning egress docs, registry logout | ✅ Merged (`5a3da58`) |
| TASK-INFRA-004 | Per-IP rate limiting at the voice TLS edge | ✅ Merged (`fb25f2c`) |

### In scope — must fix

| Ticket | Title | Status |
|---|---|---|
| TASK-DOC-004 | Truth-in-labeling: mark billing/routing/escalation/Genesys as NOT IMPLEMENTED | ✅ Merged into sprint-11 (2026-08-05): NOT IMPLEMENTED/target markers on `v1-scope.md` + cahier (5.3/5.4/F3/F6/F6bis/F8/F10) and ADR-0003/0004/0005/0015/0019/0020 headers; ADR README built-vs-target refreshed; `git diff --check` clean |
| TASK-INFRA-006 | Close/track the live-deploy open inputs (TLS, TURN, LB apply, SSH CIDR) | ✅ Merged into sprint-11 (2026-08-05): open-inputs tracker (owner/status/gate) + HAProxy/Keepalived manual apply path (VRRP-secret-from-vault) + STUN/TURN runtime wiring (`build_ice_servers`, `VOICE_TURN*`); self-owned inputs closed, platform gates named; QA voice-agent 468 + ansible 62/62 + haproxy 33/33 |
| TASK-OPS-007 | Centralized observability (OTLP collector + enable export) | ✅ Merged into sprint-11 (2026-08-06): collector+Prometheus pilot stack, one-var `otel_collector_endpoint` enablement, deterministic W3C traceparent voice→backend (one trace); QA voice-agent 476 unittest + 169 behave, ansible 69/69, haproxy 33/33 |
| TASK-WEB-022 | Latency gate remediation (meet ADR-0029 or revise it) | ✅ Merged into sprint-11 (2026-08-06): validated levers flipped to code defaults (`VOICE_BACKEND_STREAM` ON, end-of-turn hold 350 ms, warm-up ON; STT pre-warm stays OFF), ADR-0029 gate kept at 1.5 s (revision rejected) — still FAILED ~640 ms, residual → TASK-STT-014/TASK-BE-020 + platform-blocked live re-measure; QA voice-agent 476 unittest + 169 behave. User-validated on the live local stack (2026-08-06) |
| TASK-BE-025 | Streaming LLM + embedding/pgvector timeouts | ✅ Merged into sprint-11 (2026-08-05): Flux inter-signal timeout on stream + bounded-executor timeouts on embedding & pgvector query, distinct `outcome=timeout`; `mvn test` 342 green; DB-side cancel tracked as BE-026 |

### In scope — should fix

| Ticket | Title | Status |
|---|---|---|
| TASK-INFRA-007 | Deep backend health check + wired voice drain | ✅ Merged into sprint-11 (2026-08-05): haproxy `/actuator/health` + admin-socket drain delegated to LB, opt-in + non-fatal; QA haproxy 33/33 + ansible 58/58; live deferred to INFRA-006 |
| TASK-OPS-008 | Redis + Postgres backup/restore | ✅ Merged into sprint-11 (2026-08-05): backup+restore scripts `deploy/backup/`, Ansible cron + 0600 vault env files, runbook `backup-restore.md` w/ RPO/RTO; QA ansible 58/58; live restore drill deferred to INFRA-006 |
| TASK-DOC-005 | Doc freshness + backlog-index integrity | ✅ Merged into sprint-11 (2026-08-05): refreshed banners + sprint-11 "Why now"; ADR-0037 endpoint + ADR-0036/0037→Accepted; reconciled US-041/042, OQ-008, BUG-001, EPIC-011/012; `git diff --check` clean |
| BUG-007 | `/converse` ignores the KB domain filter | ✅ Merged into sprint-11 (2026-08-05): documented intentional cross-domain voice retrieval (not a leak), locked with tests, clarified query-path vs ingestion-time classifier, linked OQ-008 |
| BUG-008 | Failed TTS spans pollute `tts_first_audio` p95 | ✅ Merged into sprint-11 (2026-08-05): first-audio span emitted success-only (interrupted/failed carry elapsed on event), semantics documented; voice-agent 464 unittest green |
| TASK-WEB-024 | WebRTC concurrency ceiling + backpressure + drop per-turn batch loop | ✅ Merged into sprint-11 (2026-08-07, branch `task/TASK-WEB-024-webrtc-backpressure`): session cap `VOICE_MAX_WEBRTC_SESSIONS` (default 8) → offers past it get **503 + Retry-After** (renegotiations never capped); `voice.webrtc.active_sessions` gauge + `voice.webrtc.session_rejected` event; batch `PipecatTurnProcessor` reuses one persistent `BackgroundEventLoop` instead of `asyncio.run` per turn. QA voice-agent **487** unittest (+11) + **169** behave, `qa-validate-ansible.sh` **69/69**. Runtime-affecting (gauge/event) |
| TASK-WEB-023 | Streaming provider protocols (Gradium unlock) | ✅ Merged into sprint-11 (2026-08-07, branch `task/TASK-WEB-023-streaming-provider-protocols`): `runtime_checkable` `StreamingSttProvider`/`StreamingTtsProvider` + session protocols, per-provider streaming registry (`register_streaming_provider`/`supports_streaming`), `server.py` selection keyed off `supports_streaming()` not `== GRADIUM`, fake-vendor conformance + selection tests; QA 484 unittest / 169 behave green |

### Tracked but out of this sprint's execution (deferred)

| Ticket | Title |
|---|---|
| TASK-BE-026 | Retries on idempotent reads + LLM circuit breaker |
| TASK-OPS-006 | SHA-pin GitHub Actions + Dependabot (already ticketed) |
| TASK-INFRA-005 | Validate WebRTC signaling stickiness at the voice LB |

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
- A full OTLP observability stack: originally deferred (the inventory had **no
  collector host**). The review's **TASK-OPS-007** now brings a *minimal* collector +
  enabling OTLP export into scope so pilot p95/p99 can be aggregated; a full-blown
  observability platform remains out of scope.
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
