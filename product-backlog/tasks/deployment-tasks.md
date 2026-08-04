# Deployment tasks (Sprint 11 - remote deployment & release readiness)

Technical tasks to deploy the two-service Voice Support Bot to the
**eir-ai4cc-tst** pilot environment with a repeatable build/release process.
Environment reference: [`docs/operations/deployment-eir-ai4cc-tst.md`](../../docs/operations/deployment-eir-ai4cc-tst.md).
Architecture decision: [`ADR-0038`](../../docs/architecture/adrs/ADR-0038-pilot-deployment-architecture-eir-ai4cc-tst.md).

Locked decisions (user, 2026-08-03): Docker images + docker-compose on the app
VMs; GitHub Actions build/test/image + Ansible/SSH deploy.

Prefixes: **TASK-DEPLOY** (packaging/images), **TASK-INFRA** (infra config),
**TASK-OPS** (CI/CD, release), reusing **TASK-BE** for the backend code change.

---

## TASK-DEPLOY-001 - Backend Java Docker image

**Parent:** EPIC-012 (Pilot deployment, release & operations)
**Related decisions:** ADR-0038, ADR-0028 (observability)
**Depends on:** -
**Classification:** V1 pilot deployment
**Status:** 🚧 Implemented (2026-08-03) on `task/TASK-DEPLOY-001-backend-image` —
multi-stage `backend/Dockerfile` (Maven 3.9 / JDK 17 build → `eclipse-temurin:17-jre`
runtime) + `.dockerignore`. **Image build-validated locally** (`docker build`, ~110 s):
runs as non-root `uid=1001(app)`, fat jar 77 MB, Java 17.0.19, `EXPOSE 8080`,
`HEALTHCHECK` on `/actuator/health` (curl installed in the runtime layer), and Spring
Boot v3.4.1 boots from the image (Tomcat on 8080; fails only on the absent DB, proving
env-driven `DB_URL`). No secret baked in. Pending adversarial review ≥ 90% + QA before
merge-ready; merge on explicit user request.
**Priority:** High
**Branch:** `task/TASK-DEPLOY-001-backend-image`

### Objective

Build the Java conversation backend (`backend/`) into a reproducible, non-root
OCI image, fully configured by environment variables, ready to run under
docker-compose on `vla-t03`/`t04`.

### Scope

- Multi-stage `backend/Dockerfile`: JDK 17 build stage (`mvn -q -DskipTests
  package`), slim JRE 17 runtime stage. There is no `mvnw` today - either add the
  Maven wrapper or pin the Maven image in the build stage.
- Non-root runtime user; expose `8080`; `HEALTHCHECK` on `/actuator/health`.
- No secrets baked in; all config via env (`DB_URL`, `OLLAMA_BASE_URL`,
  `MISTRAL_API_KEY`, `CONVERSATION_API_KEY`, `CONVERSATION_STORE`, `OTEL_*`).
- `.dockerignore` to keep the build context small (exclude `target/`, tests fixtures where safe).

### Acceptance Criteria

```gherkin
Scenario: Image starts and serves health
  Given the backend image built from backend/Dockerfile
  When it runs with the tst environment variables and reachable Postgres
  Then GET /actuator/health returns UP
  And the process runs as a non-root user

Scenario: No secret in the image
  Given the built image
  When its layers and default env are inspected
  Then no API key, DB password or token is present in the image
```

### Out Of Scope

Compose wiring (TASK-INFRA-001), CI build/push (TASK-OPS-001).

---

## TASK-DEPLOY-002 - Voice bridge Python Docker image

**Parent:** EPIC-012
**Related decisions:** ADR-0038, ADR-0033 (WebRTC live transport)
**Depends on:** -
**Classification:** V1 pilot deployment
**Status:** To do (Sprint 11, branch `task/TASK-DEPLOY-002-voice-image`)
**Priority:** High
**Branch:** `task/TASK-DEPLOY-002-voice-image`

### Objective

Build the Python voice bridge (`voice-agent/`) into a reproducible, non-root OCI
image including the heavy native dependencies, binding on all interfaces.

### Scope

- `voice-agent/Dockerfile`: Python base with the system libraries `opencv`/`av`
  and `aiortc` need; `pip install -r requirements.txt`.
- Entrypoint `python -m web_voice.server --host 0.0.0.0 --port 8090`; non-root user.
- `HEALTHCHECK` on `GET /`; expose `8090`.
- Env-driven config (`VOICE_BACKEND=http`, `VOICE_BACKEND_URL`,
  `VOICE_BACKEND_API_KEY`, `GRADIUM_API_KEY`, `VOICE_STUN`, `VOICE_BACKEND_STREAM`,
  `VOICE_BACKEND_WARMUP`, `VOICE_STT_PREWARM`).
- `.dockerignore` (exclude `.venv/`, test fixtures where safe).

### Acceptance Criteria

```gherkin
Scenario: Image starts and serves the voice API
  Given the voice-bridge image built from voice-agent/Dockerfile
  When it runs with VOICE_BACKEND=http and a reachable backend
  Then GET / returns the mic UI
  And GET /api/voice/openapi.yaml returns the spec
  And the server binds 0.0.0.0:8090

Scenario: WebRTC deps present
  Given the built image
  When the WebRTC path is enabled
  Then aiortc/opencv import succeeds (no missing native lib)
```

### Out Of Scope

Compose wiring (TASK-INFRA-001), TLS/STUN provisioning (TASK-INFRA-002).

---

## TASK-BE-021 - Redis-backed conversation memory (multi-instance backend)

**Parent:** EPIC-012 (delivered in `backend/`, EPIC-005 answer engine)
**Related decisions:** ADR-0008 (Redis active sessions), ADR-0038
**Depends on:** Redis VM `.107` reachable
**Classification:** V1 pilot deployment (backend code)
**Status:** To do (Sprint 11, branch `task/TASK-BE-021-redis-conversation-memory`)
**Priority:** High
**Branch:** `task/TASK-BE-021-redis-conversation-memory`

### Objective

Share conversation memory across the two backend instances behind VIP `.11` so
multi-turn conversations survive load-balancing between `vla-t03` and `vla-t04`.
Today `InMemoryConversationMemoryAdapter` is per-process, so a turn routed to the
other instance loses history.

### Scope

- `RedisConversationMemoryAdapter` implementing the existing conversation-memory
  port (`append`, history retrieval), keyed by `conversationId`, with a TTL for
  idle sessions.
- Selection by `CONVERSATION_STORE` (`memory` default for dev/tests, `redis` on
  tst); Redis connection via env. Wire the bean by profile/flag in configuration
  (no Spring annotations in the domain).
- Follow project conventions: hexagonal, method <= 20 lines, class <= 200 lines,
  no Javadoc on ports, JUnit 5 with **manual fakes (no Mockito)**, GIVEN/WHEN/THEN.
- OpenTelemetry: keep the correlation id; add a store-mode indicator so the active
  memory backend is observable.

### Acceptance Criteria

```gherkin
Scenario: History shared across instances
  Given CONVERSATION_STORE=redis and two backend instances sharing one Redis
  And a first turn on instance A for conversation C
  When the next turn for conversation C is handled by instance B
  Then instance B reads the prior turn from Redis and answers with context

Scenario: In-memory default unchanged
  Given CONVERSATION_STORE unset
  Then the in-process memory adapter is used and existing tests pass

Scenario: Redis unavailable degrades safely
  Given CONVERSATION_STORE=redis and Redis unreachable
  Then the failure is handled without crashing the turn and is observable
```

### Out Of Scope

Durable event store / Postgres event log (ADR-0008 second half); session
draining (TASK-OPS-002).

---

## TASK-INFRA-001 - docker-compose deploy stacks + env templates

**Parent:** EPIC-012
**Related decisions:** ADR-0038
**Depends on:** TASK-DEPLOY-001, TASK-DEPLOY-002
**Classification:** V1 pilot deployment
**Status:** To do (Sprint 11, branch `task/TASK-INFRA-001-compose-stacks`)
**Priority:** High
**Branch:** `task/TASK-INFRA-001-compose-stacks`

### Objective

Provide the per-tier docker-compose stacks and `.env` templates that run the
images on the tst VMs and wire them to Postgres, Redis and the cloud providers.

### Scope

- `deploy/compose/backend/docker-compose.yml` + `.env.example` (backend on
  `vla-t03`/`t04` -> Postgres `.102`, Redis `.107`, embeddings host, Mistral).
- `deploy/compose/voice/docker-compose.yml` + `.env.example` (voice on
  `vla-t01`/`t02` -> backend VIP `.11`, Gradium).
- `deploy/compose/redis/docker-compose.yml` + `.env.example` (Redis on `.107`),
  unless the platform provides Redis natively.
- Restart policy, resource limits sized to the flavors, log rotation, healthchecks
  surfaced to compose. `.env` files are rendered by Ansible from secrets (never committed).

### Acceptance Criteria

```gherkin
Scenario: Backend stack up
  Given the backend compose and a rendered .env on vla-t03
  When docker compose up -d runs
  Then the backend container is healthy and reaches Postgres and Redis

Scenario: Voice stack up
  Given the voice compose and a rendered .env on vla-t01
  When docker compose up -d runs
  Then the bridge is healthy and reaches the backend VIP
```

### Out Of Scope

LB/VIP config (TASK-INFRA-002), CI (TASK-OPS-001), Ansible orchestration (TASK-OPS-002).

---

## TASK-INFRA-002 - HAProxy + Keepalived VIP configuration

**Parent:** EPIC-012
**Related decisions:** ADR-0038, ADR-0033 (WebRTC/TLS)
**Depends on:** TASK-INFRA-001 (running backends), platform team coordination
**Classification:** V1 pilot deployment
**Status:** To do (Sprint 11, branch `task/TASK-INFRA-002-haproxy-vips`)
**Priority:** High
**Branch:** `task/TASK-INFRA-002-haproxy-vips`

### Objective

Configure the two VIPs on the HAProxy/Keepalived pair (`vlp-t01`/`t02`) so voice
and backend traffic is load-balanced across the two instances of each tier, with
health checks, finalized ports and TLS at the voice edge.

### Scope

- Voice VIP `.10` (Prodpriv, `10.195.59.39`) -> `.103`/`.104:8090`; **TLS
  termination** for HTTPS/WSS (WebRTC signaling; confirm media/UDP handling with
  the platform team).
- Backend VIP `.11` (internal) -> `.105`/`.106:8080`.
- Health checks: voice `GET /`, backend `GET /api/health` (both ungated).
- Keepalived VRRP failover across the two AZs; finalize the placeholder ports.
- Document the config under `deploy/haproxy/` (or hand off to the platform team
  if HAProxy is platform-managed) and in the environment doc.

### Acceptance Criteria

```gherkin
Scenario: Backend VIP load-balances two instances
  Given both backends healthy behind VIP .11
  When requests hit the VIP
  Then they are distributed and an unhealthy instance is removed from rotation

Scenario: Voice VIP terminates TLS
  Given a certificate installed for the voice VIP FQDN
  When a client connects over HTTPS/WSS to VIP .10
  Then TLS terminates at HAProxy and the WebRTC signaling reaches a bridge

Scenario: Failover
  Given the active LB node fails
  Then Keepalived moves the VIP to the standby node without dropping the VIP
```

### Out Of Scope

Certificate issuance policy and STUN/TURN provisioning (open inputs); app config.

---

## TASK-INFRA-003 - Embeddings placement + provider egress decision

**Parent:** EPIC-012
**Related decisions:** ADR-0038, ADR-0006 (Mistral chat / Ollama embeddings), ADR-0030
**Depends on:** confirmed tst egress policy (open input)
**Classification:** V1 pilot deployment (decision/spike)
**Status:** To do (Sprint 11, branch `task/TASK-INFRA-003-embeddings-egress`)
**Priority:** High (blocks a functional backend on tst)
**Branch:** `task/TASK-INFRA-003-embeddings-egress`

### Objective

Decide and document how embeddings run on tst (no Ollama/GPU host is provisioned)
and confirm the internet egress the cloud providers need. The backend cannot
start ingestion/RAG without a reachable embedding model.

### Scope

- Evaluate options and record an ADR addendum / decision:
  - (a) Ollama `nomic-embed-text` on CPU, co-located on the backend VMs or the DB
    VM (768 dim, no table change, no cloud egress for embeddings).
  - (b) Switch to Mistral embeddings (1024 dim -> recreate `vector_store`, full
    re-sync, cloud egress). See CLAUDE.md dimension caveats.
- Confirm egress to `api.mistral.ai`, the Gradium API, and the container registry
  (direct or via proxy).
- Capture the outcome in `docs/operations/deployment-eir-ai4cc-tst.md` and, if it
  changes the architecture, an ADR (addendum to ADR-0006/ADR-0038).

### Acceptance Criteria

```gherkin
Scenario: Embeddings reachable on tst
  Given the chosen embeddings option deployed/configured
  When the backend performs a KB sync and a retrieval
  Then embeddings are produced and vector search returns results with no dimension mismatch
```

### Out Of Scope

Self-hosted LLM/STT/TTS (infra-v1 GPU option) - not a pilot prerequisite.

---

## TASK-OPS-001 - GitHub Actions CI (test + build/push images)

**Parent:** EPIC-012
**Related decisions:** ADR-0038
**Depends on:** TASK-DEPLOY-001, TASK-DEPLOY-002; registry access (open input)
**Classification:** V1 pilot deployment (CI)
**Status:** To do (Sprint 11, branch `task/TASK-OPS-001-github-actions-ci`)
**Priority:** High
**Branch:** `task/TASK-OPS-001-github-actions-ci`

### Objective

Automate quality gates and image builds on `tgrimaud/V2V` with GitHub Actions,
publishing versioned images to the container registry. (GitHub Actions is native
to the repo; no Cursor GitHub App is required for CI.)

### Scope

- Workflow(s) under `.github/workflows/`:
  - Test gate: backend `mvn test`; voice-agent `unittest` + `behave` (via the
    venv/requirements as in CLAUDE.md).
  - Build + push both images on a release tag / main, tagged with the git SHA
    and a semantic release tag.
- Registry auth via repo/org secrets; no secrets in logs.
- Define the image tag/version scheme reused by the Ansible deploy (TASK-OPS-002).

### Acceptance Criteria

```gherkin
Scenario: PR runs the gates
  Given a pull request
  Then backend mvn test and voice-agent unittest+behave run and must pass

Scenario: Release publishes tagged images
  Given a release tag
  Then both images are built and pushed with an immutable version tag
```

### Out Of Scope

Deployment to the VMs (TASK-OPS-002); Bugbot/Cloud-Agents GitHub App (optional, unrelated to CI).

---

## TASK-OPS-002 - Ansible deploy playbooks + release/rollback runbook

**Parent:** EPIC-012
**Related decisions:** ADR-0038, ADR-0010 (industrialization gate)
**Depends on:** TASK-INFRA-001, TASK-OPS-001; secrets store (open input)
**Classification:** V1 pilot deployment (release)
**Status:** To do (Sprint 11, branch `task/TASK-OPS-002-ansible-release`)
**Priority:** High
**Branch:** `task/TASK-OPS-002-ansible-release`

### Objective

Deploy a released image set to the tst VMs over SSH with Ansible, reproducibly,
with a documented rollback and voice session draining.

### Scope

- `deploy/ansible/` inventory (the 8 VMs, per-tier groups) + playbooks: render
  `.env` from secrets (Ansible vault), `docker compose pull` + `up -d` per tier.
- Voice **session draining** before restarting a bridge (avoid cutting active calls).
- **Rollback** by redeploying the previous image tag.
- Author `docs/operations/release-process.md`: prerequisites, promote a version,
  deploy order (backend before voice), verification, rollback, secrets handling.

### Acceptance Criteria

```gherkin
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

### Out Of Scope

CI image build (TASK-OPS-001); HAProxy config (TASK-INFRA-002).

---

## TASK-DOC-003 - Deployment documentation sync + operational runbook

**Parent:** EPIC-012
**Related decisions:** ADR-0038
**Depends on:** the other Sprint 11 tickets (kept in sync as they land)
**Classification:** V1 pilot deployment (docs)
**Status:** To do (Sprint 11, branch `task/TASK-DOC-003-deployment-docs`)
**Priority:** Medium
**Branch:** `task/TASK-DOC-003-deployment-docs`

### Objective

Keep the deployment docs accurate as tickets land and author the first-deploy
operational runbook (a delivery engineer can go from zero to a running pilot).

### Scope

- Maintain `docs/operations/deployment-eir-ai4cc-tst.md` (resolve open inputs as
  they are answered; keep the port matrix and env tables current).
- First-deploy checklist: SSH access, Postgres DB + `CREATE EXTENSION vector`,
  Redis up, secrets in the vault, deploy order, smoke test (a full voice turn),
  known-good rollback.
- Cross-links: `docs/architecture/infra-v1.md`, `docs/README.md`,
  `docs/operations/development-workflow.md`.

### Acceptance Criteria

```gherkin
Scenario: Runbook is executable
  Given a clean tst environment and the runbook
  When a delivery engineer follows it
  Then they reach a passing end-to-end voice smoke test without tribal knowledge
```

### Out Of Scope

The generic operator target (infra-v1.md) - only cross-linked, not rewritten.
