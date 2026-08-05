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
**Status:** ✅ **Merged into `feat/sprint-11-remote-deployment`** (2026-08-04, `--no-ff` `ee42541`)
— built on `task/TASK-DEPLOY-001-backend-image` (rides to `feat/restart-from-scratch` at sprint
closure).
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
**Status:** ✅ **Merged into `feat/sprint-11-remote-deployment`** (2026-08-04, `--no-ff` `579fcc9`)
— built on `task/TASK-DEPLOY-002-voice-image` (rides to `feat/restart-from-scratch` at sprint
closure).
`voice-agent/Dockerfile` (`python:3.12-slim` + `libgl1`/`libglib2.0-0` for cv2) +
`.dockerignore`. **Image build-validated locally** (`docker build`, ~76 s): heavy deps
import (pipecat 1.7.0, cv2 4.14.0, aiortc 1.15.0), runs as non-root `uid=1001`,
`EXPOSE 8090`, python-based `HEALTHCHECK` on `GET /`. **Runtime smoke** (with a dummy
`GRADIUM_API_KEY`): server binds `0.0.0.0:8090` (webrtc=on), `GET /` → 200 and
`GET /api/voice/openapi.yaml` → 200. Confirmed the provider requires `GRADIUM_API_KEY`
at startup (a required secret, already in the env doc). Image ~1.82 GB (opencv/av);
`opencv-python-headless` is a later size lever (ADR-0022). Pending adversarial review
≥ 90% + QA before merge-ready; merge on explicit user request.
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
**Status:** ✅ **Merged into `feat/sprint-11-remote-deployment`** (2026-08-04, `--no-ff` `daa2102`;
adversarial 92/100 → QA GO) — built on
`task/TASK-BE-021-redis-conversation-memory` (rides to `feat/restart-from-scratch` at sprint
closure). Post-merge integrated `mvn test` **336** green, ArchUnit OK. — `RedisConversationMemoryAdapter` (bounded Redis
list per conversation, sliding idle TTL, JSON turns) behind a `ConversationTurnStore` seam with a
`RedisConversationTurnStoreAdapter` (StringRedisTemplate: RPUSH + LTRIM + EXPIRE). Selected by
`CONVERSATION_STORE=redis` (default `memory`), wired in `ConversationConfig` via
`ObjectProvider<StringRedisTemplate>` so `memory` mode never needs a Redis bean. Added
`spring-boot-starter-data-redis` (BOM) + `spring.data.redis.*`
(`REDIS_HOST`/`PORT`/`PASSWORD`/`TIMEOUT`). A Redis outage degrades to empty history (logged
`[CONVERSATION-MEMORY]`, `voice_support.conversation_memory.degraded` counter) instead of failing
the turn; a corrupt/legacy entry is skipped, not fatal; active store logged at startup.
**Adversarial-review blocking fix applied:** the Redis health indicator (auto-registered by the new
starter) is gated `management.health.redis.enabled=${REDIS_HEALTH_ENABLED:false}` so `/actuator/health`
stays UP in the default `memory` mode (else it would ping localhost:6379 → DOWN → HAProxy/HEALTHCHECK
drops the instance). **`mvn test` 330 green (+10, ArchUnit OK)**;
`RedisConversationMemoryAdapterTest` (fake, no Mockito: round-trip, bound, isolation, blank id,
special chars, TTL, corrupt-entry skip, outage-degrade) + `RedisHealthIndicatorGateTest`
(gate off → no `redisHealthContributor`; on → present). **Live smoke (Postgres+Ollama up):** memory
mode → `/actuator/health` UP, no `redis` component; `REDIS_HEALTH_ENABLED=true` → `redis` component
participates. Live multi-instance shared-context is INFRA-001 integration. Merge on explicit user request.
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
**Status:** 🚧 Implemented (2026-08-04) on `task/TASK-INFRA-001-compose-stacks` — per-tier
stacks `deploy/compose/{backend,voice,redis}/docker-compose.yml` + `.env.example`, a
`deploy/compose/README.md` and a `.gitignore` that versions only the templates. Env-driven
image ref (`${*_IMAGE}:${IMAGE_TAG}`), healthchecks mirroring the image `HEALTHCHECK`s,
`restart: unless-stopped`, per-flavor resource limits, json-file log rotation. All three
validated with `docker compose config` (v29.1.3). Open inputs (registry, embeddings host,
egress, STUN/TLS, DB/Redis creds) surfaced as documented `.env.example` placeholders rather
than guessed. **Adversarial review 93/100 (Pass, 2026-08-04)** — blocking fix applied: the
backend image ships only the jar, so the KB is now mounted read-only from `KB_HOST_PATH`
(`/app/kb-assets`, directory bind) and synced into pgvector on first run, instead of pointing
at non-existent image paths. Residual (accepted, pilot): secrets via `docker inspect`,
`0.0.0.0` publish gated by INFRA-002, `REDIS_HEALTH_ENABLED=true` tier-scoped.
**QA GO (2026-08-04)** — `deploy/compose/qa-validate.sh` 22/22 deterministic checks green
(renders + healthchecks + KB read-only mount + secret hygiene + key parity);
[QA report](../../docs/qa/task-infra-001-compose-stacks-qa-report.md). Live "reaches
Postgres/Redis/VIP" smoke deferred to tst (open inputs). ✅ **Merged into
`feat/sprint-11-remote-deployment`** (2026-08-04, `--no-ff` `9fef902`; rides to
`feat/restart-from-scratch` at sprint closure).
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
**Status:** ✅ Implemented — adversarial 92/100 (Pass; VRRP unicast + ip_nonlocal_bind
fixes); QA GO (`deploy/haproxy/qa-validate-haproxy.sh` 25/25 incl. real `haproxy -c`,
[report](../../docs/qa/task-infra-002-haproxy-vips-qa-report.md)); live VIP/TLS/failover
deferred to the LB hosts (platform open inputs). ✅ **Merged into
`feat/sprint-11-remote-deployment`** (2026-08-04, `--no-ff` `f2cc838`; rides to
`feat/restart-from-scratch` at sprint closure).
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
**Status:** ✅ Implemented — decision **ADR-0039** (Ollama `nomic-embed-text` CPU
sidecar co-located per backend VM; Mistral embeddings rejected); backend compose +
Ansible wired (sidecar + deploy-time model pull), dim stays 768. Adversarial 92/100
(Pass; deploy-time Ollama-registry egress fix); QA GO (compose config + Ansible 33/33
+ compose 22/22, [report](../../docs/qa/task-infra-003-embeddings-egress-qa-report.md));
live tst sync/retrieval deferred. ✅ **Merge-ready** (merge on the user's explicit
request). Branch `task/TASK-INFRA-003-embeddings-egress`
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

## TASK-INFRA-004 - HAProxy edge rate limiting (per-IP burst control at the voice TLS edge)

**Parent:** EPIC-012
**Related decisions:** ADR-0038, ADR-0033 (WebRTC/TLS edge)
**Depends on:** TASK-INFRA-002 (HAProxy/Keepalived config)
**Classification:** V1 pilot deployment (edge security hardening)
**Status:** 🚧 Implemented on `task/TASK-INFRA-004-haproxy-edge-rate-limit`
(from `feat/sprint-11-remote-deployment`, 2026-08-05). QA green: `qa-validate-haproxy.sh`
**30/30** incl. a real `haproxy -c` parse of the rate-limited config (via the haproxy:2.8
container). Live burst test deferred to the LB hosts. Merge on explicit user request.
**Priority:** Low
**Branch:** `task/TASK-INFRA-004-haproxy-edge-rate-limit`
**Surfaced by:** Sprint 11 full adversarial code+doc review (2026-08-05) — low-severity
finding: the public TLS edge had no rate limiting, so a single client could flood the
signaling/UI surface and the bridges behind it.

### Context

INFRA-002 stood up the voice TLS edge (`.10:443`) with roundrobin LB + health checks but
**no abuse control**. On a public/Prodpriv edge, an unbounded client can open connections
and issue signaling/UI requests as fast as it likes, exhausting bridge resources. WebRTC
*media* is UDP peer-to-peer (not proxied), so only the HTTP signaling/UI surface is exposed
here — but that surface still fronts the bridges and deserves a burst ceiling.

### Scope

- Add a per-source-IP stick-table on the **voice** frontend tracking `conn_rate` +
  `http_req_rate` (10s windows); reject connection-rate bursts at accept and deny
  request-rate bursts with **429**, before the bridges.
- Keep the **internal** backend frontend (`.11:8080`, LB→backend only) unrate-limited.
- Pilot-tuned thresholds (generous for a browser), documented as tunable; media never
  affected.

### Acceptance

- The voice frontend carries the stick-table + `track-sc0` + a connection-rate reject +
  an http-request 429 deny; the config still passes `haproxy -c`.
- The rate limit is scoped to the voice edge, not the internal backend frontend.
- `qa-validate-haproxy.sh` stays green with the new checks.

### Implementation notes (2026-08-05)

- `haproxy.cfg` voice frontend: `stick-table type ip size 100k expire 10m store
  conn_rate(10s),http_req_rate(10s)`; `tcp-request connection track-sc0 src`;
  `tcp-request connection reject if { sc0_conn_rate gt 50 }`;
  `http-request deny deny_status 429 if { sc0_http_req_rate gt 100 }`.
- `qa-validate-haproxy.sh`: +5 checks (stick-table counters, source tracking, conn-rate
  reject, 429 request-rate deny, and an `awk` scope check that the stick-table is under the
  voice frontend, not the backend one) → **30/30** with the container `haproxy -c` parse.
- `README.md`: new "Edge rate limiting" section (config snippet, pilot-threshold note,
  media-not-affected caveat).

### Residual (accepted / deferred)

- **Threshold tuning + a live burst test** need real traffic + LB-host access — deferred;
  the parse + structural checks are deterministic.
- Distributed floods (many source IPs) are out of scope for a per-IP table; a WAF / global
  concurrency cap is a later hardening if the pilot goes wider.

---

## TASK-OPS-003 - Host prerequisites (Docker Engine + compose plugin) via Ansible

**Parent:** EPIC-012
**Related decisions:** ADR-0038 (Docker + compose on the app VMs)
**Depends on:** SSH access to the VMs (open input #1)
**Classification:** V1 pilot deployment (host provisioning)
**Status:** ✅ Implemented — `host_prereqs` role + `prereqs.yml` (Docker Engine +
compose v2 + buildx, service enable, docker group, tier-aware firewalld). Adversarial
92/100 (Pass; Rocky EL9 podman/runc conflict fixed via `allowerasing`); QA GO 21/21 +
OPS-002 33/33 no regression ([report](../../docs/qa/task-ops-003-docker-host-prereqs-qa-report.md));
live run deferred (VM network access, #1). ✅ **Merge-ready** (merge on explicit user request).
**Priority:** High (blocks the first deploy - the compose_tier role assumes Docker exists)
**Branch:** `task/TASK-OPS-003-docker-host-prereqs`

### Objective

The `compose_tier` role (TASK-OPS-002) runs `docker compose pull/up` but **assumes
Docker is already installed**. The tst VMs are bare Rocky Linux EL9, so a first
deploy fails with "docker: command not found". Add an idempotent Ansible play that
provisions the container runtime on the redis/backend/voice VMs before deployment.

### Scope

- New `host_prereqs` role: install **Docker Engine** (docker-ce, cli, containerd) +
  **compose v2 plugin** + buildx from the official Docker CE repo on Rocky EL9
  (dnf), enable/start the service, add the deploy user to the `docker` group.
- Tier-aware **firewalld** opening of the published port (redis 6379, backend 8080,
  voice 8090) when firewalld is active, so cross-VM traffic (backend↔redis, VIP↔tier)
  works - guarded, no-op when firewalld is inactive.
- Standalone `prereqs.yml` playbook (run once per fresh host); documented in the
  Ansible README + release runbook. Not folded into `deploy.yml` to keep deploys fast.
- Note SELinux: the KB `:ro` bind mount may need `:Z` relabeling on enforcing hosts
  (documented; compose change tracked as a follow-up if the first deploy hits AVC denials).

### Acceptance Criteria

```gherkin
Scenario: A bare Rocky EL9 VM is ready to run compose stacks
  Given a fresh redis/backend/voice VM with SSH access
  When prereqs.yml runs against it
  Then docker + the compose v2 plugin are installed and the service is enabled
  And re-running prereqs.yml reports no changes (idempotent)
```

### Out Of Scope

Kubernetes/podman; Docker install on the DB VM (`.102`, platform-managed Postgres pod)
and the LB VMs (HAProxy, native). Image publication (TASK-OPS-001) and the deploy
itself (TASK-OPS-002).

### Residual (accepted for the pilot)

- ~~The tier port is opened in the **default firewalld zone** (Redis 6379 with auth on).
  Restricting the source to the backend subnet (rich rule) is a hardening follow-up.~~
  ✅ **Closed by TASK-OPS-004** (2026-08-05): the port is now opened with **source-scoped
  firewalld rich rules** (Redis 6379 only to the backend VMs; backend/voice ports only to
  the LB nodes), with the unscoped `--add-port` kept only as an empty-list fallback.
- SELinux `:Z` relabel of the KB `:ro` mount is documented, applied only if the first
  deploy hits an AVC denial.

---

## TASK-OPS-004 - Deploy hardening: source-scoped firewalld, provisioning egress, registry logout

**Parent:** EPIC-012
**Related decisions:** ADR-0038, ADR-0039 (egress)
**Depends on:** TASK-OPS-002 (compose_tier role), TASK-OPS-003 (host_prereqs firewalld)
**Classification:** V1 pilot deployment (security + docs hardening)
**Status:** 🚧 Implemented on `task/TASK-OPS-004-deploy-egress-firewall-hardening`
(from `feat/sprint-11-remote-deployment`, 2026-08-05). QA green: `qa-validate-prereqs.sh`
**28/28** (+7), `qa-validate-ansible.sh` **35/35** (+2), both playbooks `--syntax-check`
clean. Live run deferred (VM network access, open input #1). Merge on explicit user request.
**Priority:** Medium
**Branch:** `task/TASK-OPS-004-deploy-egress-firewall-hardening`
**Surfaced by:** Sprint 11 full adversarial code+doc review (2026-08-05) — three non-blocking
findings (one medium: undocumented provisioning egress; two low/medium: permissive firewalld
default-zone scope + registry credential left cached after pull).

### Context

The Sprint 11 review confirmed the deployment stack is sound but flagged three hardening
gaps before an off-box posture:

- **Firewalld default-zone scope (medium).** `host_prereqs` opened each tier's port to
  **everyone** in the default zone (Redis 6379, backend 8080, voice 8090). Even with Redis
  auth on, the ports should only accept their real clients. (OPS-003 tracked this as a
  residual.)
- **Undocumented provisioning egress (medium).** The runtime egress allowlist (ADR-0039:
  Mistral, Gradium, GHCR, `registry.ollama.ai`) omitted the **one-time host bootstrap**
  egress `prereqs.yml` needs: `download.docker.com` (Docker CE repo + packages) and the
  Rocky EL9 OS mirrors. On a locked-down tenant the first `prereqs.yml` would fail silently.
- **Registry credential at rest (low).** `compose_tier` ran `docker login` before the pull
  but never logged out, leaving the read-only PAT cached in `~/.docker/config.json`.

### Scope

- **Source-scoped firewalld** in `host_prereqs`: open the port via `--add-rich-rule` limited
  to a per-tier `firewall_allowed_sources` list (Redis → backend VMs `.105/.106`;
  backend/voice → LB nodes `.100/.101`), keeping the unscoped `--add-port` only as an
  empty-list fallback. Idempotent (`ALREADY_ENABLED`), guarded on firewalld active, no
  external collection.
- **Registry logout** in `compose_tier` after `up -d` (gated on `registry_login_required`,
  `no_log`), so the token does not linger; the next deploy logs in again.
- **Provisioning egress** documented in the deployment doc (open input #2 + port matrix):
  `download.docker.com` + Rocky EL9 mirrors, clearly marked bootstrap-only.

### Acceptance

- Each tier port is opened only to its documented source IPs (rich rules); the unscoped
  fallback fires only when the source list is empty.
- The registry credential is dropped after the pull.
- The provisioning-time egress is documented alongside the runtime egress.
- Both Ansible QA suites stay green (deterministic); playbooks `--syntax-check` clean.

### Implementation notes (2026-08-05)

- `roles/host_prereqs/tasks/main.yml`: split the firewalld open into a **rich-rule loop**
  over `firewall_allowed_sources` (argv form keeps the rule string intact) and an
  empty-list **fallback** `--add-port`; the reload fires when either path changed.
- `group_vars/{redis,backend,voice}.yml`: added `firewall_allowed_sources` (Redis → the two
  backend VMs; backend + voice → the two LB nodes, since both app tiers are reached only
  through their VIP on an LB node).
- `roles/compose_tier/tasks/main.yml`: added a `docker logout {{ registry }}` step after
  `up -d`, gated + `no_log`.
- `docs/operations/deployment-eir-ai4cc-tst.md`: open input #2 now lists the provisioning
  egress; the port matrix gained the `download.docker.com`/mirrors, GHCR and
  `registry.ollama.ai` rows.
- QA: `qa-validate-prereqs.sh` +7 checks (rich-rule scoping, per-tier source IPs, fallback
  gating, egress doc) → **28/28**; `qa-validate-ansible.sh` +2 (logout after login, gated) →
  **35/35**.

### Residual (accepted / deferred)

- **Live verification** (rich rules actually applied, ports reachable only from the listed
  sources) needs VM access (open input #1) — the checks here are deterministic/offline.
- SSH (22) is untouched (its own firewalld service); the SSH source range is still open
  input #1.

---

## TASK-OPS-001 - GitHub Actions CI (test + build/push images)

**Parent:** EPIC-012
**Related decisions:** ADR-0038
**Depends on:** TASK-DEPLOY-001, TASK-DEPLOY-002; registry access (open input)
**Classification:** V1 pilot deployment (CI)
**Status:** 🚧 Implemented (2026-08-04) on `task/TASK-OPS-001-github-actions-ci` — two
workflows under `.github/workflows/`: `ci.yml` (test gate on PR + mainline/sprint/ticket
pushes: backend `mvn test` on Temurin 17 with Maven cache; voice-agent `unittest` + `behave`
on Python 3.12, installing `libgl1`/`libglib2.0-0` for the cv2 import like the Dockerfile)
and `images.yml` (build + push both images to **GHCR** with `GITHUB_TOKEN` on `v*.*.*` tags,
`latest` on the default branch, `sha-<short>` always; buildx + gha cache). Registry = GHCR by
default (native, no extra secret); override path for an internal Nexus/Artifactory documented
in the workflow header (open input #5). Validated with `actionlint` (clean) + YAML parse.
**Adversarial review 93/100 (Pass, 2026-08-04)** — blocking fix applied: extracted a reusable
`tests.yml` (`workflow_call`) consumed by both `ci.yml` and `images.yml` with
`build-push: needs: tests`, so a release tag can no longer publish an untested image; `ci.yml`
push scoped to the mainline (no duplicate PR+push runs). Residual (accepted): `latest` tracks
the integration branch; image build re-runs the app build (buildx/gha cache mitigates).
**QA GO (2026-08-04)** — `.github/qa-validate-workflows.sh` 22/22 deterministic checks green
(lint, reusable-gate wiring, publish scheme, fork-safe triggers, least-privilege, secret
hygiene); [QA report](../../docs/qa/task-ops-001-github-actions-ci-qa-report.md). Live GitHub
Actions run (PR gate + tag publish) verified on the first PR/tag post-merge. ✅ **Merged into
`feat/sprint-11-remote-deployment`** (2026-08-04, `--no-ff` `1e431f2`; rides to
`feat/restart-from-scratch` at sprint closure).
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
**Status:** ✅ Implemented — adversarial 93/100 (Pass; KB provisioning + Redis auth
fixes applied); QA GO (`deploy/ansible/qa-validate-ansible.sh` 33/33,
[report](../../docs/qa/task-ops-002-ansible-release-qa-report.md)); live tst
deploy/rollback/drain deferred to first deploy. ✅ **Merged into
`feat/sprint-11-remote-deployment`** (2026-08-04, `--no-ff` `20f1770`; rides to
`feat/restart-from-scratch` at sprint closure).
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
**Status:** ✅ Implemented (2026-08-05, branch `task/TASK-DOC-003-deployment-docs`) — first-deploy runbook authored + docs synced (incl. the image-tag `X.Y.Z` no-`v` correction found when publishing `0.4.0`). Not runtime-affecting (docs + one Ansible comment).
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

### Implementation notes (2026-08-05)

- **New:** `docs/operations/first-deploy-runbook.md` — chronological zero-to-running
  runbook (access + open inputs, publish images, vault, `prereqs.yml`, Postgres
  bootstrap + `CREATE EXTENSION vector`, deploy Redis → backend + first RAG sync →
  voice, LB/TLS edge, two-tier smoke test, known-good rollback, first-deploy
  troubleshooting table). Grounded on the real backend endpoints (`/api/health`,
  `POST /api/conversation/converse` with snake_case body + `x-api-key`,
  `POST /api/knowledge/sync`).
- **Accuracy fix (image tag has no `v`):** `docker/metadata-action`
  `type=semver,pattern={{version}}` strips the leading `v`, so git tag `vX.Y.Z`
  publishes image tag `X.Y.Z`. Corrected `release-process.md`,
  `deploy/ansible/README.md`, `group_vars/all/vars.yml` (comment) and open input #5
  in `deployment-eir-ai4cc-tst.md`; deploy uses `-e image_tag=0.4.0`, not `v0.4.0`.
- **Cross-links:** runbook linked from `docs/README.md`,
  `deployment-eir-ai4cc-tst.md`, `release-process.md`, `infra-v1.md` and
  `development-workflow.md`.
- **QA:** `docs/qa/task-doc-003-deployment-docs-qa-report.md` (link + accuracy
  checks). Live tst run of the runbook deferred to network access (open input #1).

---

## TASK-INFRA-005 - Validate WebRTC signaling stickiness at the voice LB (or add it)

**Parent:** EPIC-012
**Related decisions:** ADR-0033 (WebRTC single live transport), ADR-0038
**Depends on:** TASK-INFRA-002 (voice VIP), live bridge access (open input #1/#4)
**Classification:** V1 pilot deployment (correctness validation)
**Status:** Proposed (2026-08-05) — **ticket only, deferred** (needs a live two-bridge run;
cannot be settled by static analysis).
**Priority:** Medium
**Surfaced by:** Sprint 11 full adversarial code+doc review (2026-08-05) — the voice
`backend voice_bridges` uses **roundrobin with no stickiness**, resting on the assumption
(comment in `haproxy.cfg`) that WebRTC signaling is a *single* HTTP request so subsequent
media pins peer-to-peer to the answering bridge.

### Context

`deploy/haproxy/haproxy.cfg` load-balances the two bridges roundrobin and states "No
stickiness needed: the SDP offer POST establishes the session on the bridge that answers,
and media pins to that bridge's ICE candidate." If the browser only ever makes **one**
signaling call (the SDP offer) and everything else is UDP P2P, that holds. But if the
signaling flow is **multi-request** — e.g. trickle-ICE candidate POSTs, a separate GET for
the SDP answer, or a renegotiation — a second request can roundrobin to the **other**
bridge, which holds no `RTCPeerConnection` for that session, and the call fails to
establish. This is a correctness risk that only shows up live.

### Objective

Confirm the signaling is genuinely single-shot on the real bridge, or make the LB pin all
of a session's signaling to the bridge that answered the offer.

### Scope

- Inspect `web_voice` signaling: is the WebRTC offer/answer a single HTTP round-trip, or
  are there follow-up signaling requests (trickle ICE, answer polling, renegotiation)?
- Live test through the VIP with both bridges up: establish several calls and confirm each
  session's signaling + media reach one bridge (no cross-bridge failure).
- **If** multi-request: add stickiness on `voice_bridges` (e.g. `cookie`/`stick on src` or a
  session-scoped key) so all signaling of one session pins to the answering bridge; re-run.

### Acceptance

- Evidence (live) that N concurrent calls each establish correctly through the VIP, or a
  stickiness rule added + re-validated. Update the `haproxy.cfg` comment to match reality.

### Notes

- Do not add stickiness blindly: if signaling really is single-shot, roundrobin is correct
  and stickiness would only reduce spread. The point is to *verify*, then decide.

---

## TASK-OPS-006 - Pin GitHub Actions to commit SHAs (supply-chain hardening)

**Parent:** EPIC-012
**Related decisions:** ADR-0038
**Depends on:** TASK-OPS-001 (the workflows)
**Classification:** V1 pilot deployment (CI supply-chain hardening)
**Status:** Proposed (2026-08-05) — **ticket only, deferred** (low risk for a private-repo
pilot; recommended before wider exposure).
**Priority:** Low
**Surfaced by:** Sprint 11 full adversarial code+doc review (2026-08-05) — the CI workflows
reference third-party actions by **mutable major-version tags**, not immutable commit SHAs.

### Context

`.github/workflows/*.yml` pin actions to floating tags: `actions/checkout@v4`,
`actions/setup-java@v4`, `actions/setup-python@v5`, `docker/metadata-action@v5`,
`docker/setup-buildx-action@v3`, `docker/login-action@v3`, `docker/build-push-action@v6`.
A moved tag (compromise or a breaking republish) would run unreviewed third-party code in a
workflow that holds `GITHUB_TOKEN` / GHCR push. Pinning to a **commit SHA** makes each
action immutable; the risk is low on a private repo but is a standard supply-chain hardening.

### Scope

- Repin each third-party `uses:` to a full commit SHA (keep a `# vX.Y.Z` trailing comment
  for readability). The local reusable `./.github/workflows/tests.yml` is not affected.
- Add **Dependabot** (`.github/dependabot.yml`, `package-ecosystem: github-actions`) so the
  SHAs are bumped by reviewed PRs rather than drifting silently.
- Re-run `actionlint` + `.github/qa-validate-workflows.sh`; keep the reusable-gate wiring.

### Acceptance

- Every third-party action is pinned to a commit SHA; Dependabot tracks updates;
  `actionlint` + the workflow QA stay green.

### Notes

- Deferred, not blocking: acceptable on the current private-repo pilot. Do it before the
  repo/CI surface widens or the images gain external consumers.

---

## TASK-INFRA-006 - Close the live-deploy open inputs (make the tst pilot runnable)

**Parent:** EPIC-012
**Related decisions:** ADR-0038, ADR-0033
**Depends on:** platform team (external inputs), TASK-INFRA-002
**Classification:** V1 pilot deployment (go-live blocker)
**Status:** 📋 Open — ready to start (tracking + the parts we own)
**Priority:** High
**Branch:** `task/TASK-INFRA-006-close-deploy-open-inputs`
**Surfaced by:** Sprint 11 full adversarial code+doc review (2026-08-05,
`docs/architecture/reviews/full-adversarial-review-2026-08-05.md`) — the two-service stack
**cannot run live** on eir-ai4cc-tst until a set of external inputs is closed.

### Context

Several inputs block the first live deployment and are not code we can merge alone:
TLS cert + FQDN for the voice VIP (`haproxy.cfg:40`, no cert at `/etc/haproxy/certs/voice-vip.pem`),
`VOICE_STUN=""` so WebRTC media cannot traverse for Prodpriv clients (`group_vars/voice.yml:37-38`),
HAProxy/keepalived not automated by Ansible (committed `CHANGE_ME_VRRP`, `keepalived-vlp-t01.conf:38`),
and undocumented SSH/ingress source CIDRs. Static QA is green; nothing more can be proven
without these.

### Scope

- Track each open input with an owner + due date; mirror the list in
  `docs/operations/deployment-eir-ai4cc-tst.md` (open inputs) and the first-deploy runbook.
- Own-able parts: provide the HAProxy/keepalived apply path (playbook or documented manual
  steps incl. `ip_nonlocal_bind`, VRRP secret handling, interface name), and the STUN/TURN
  config wiring (`VOICE_STUN`/`VOICE_TURN` env → voice `.env`).
- Parts blocked on the platform: TLS cert issuance + FQDN, SSH/ingress CIDR allowlist.

### Acceptance

- Every open input has an owner + status; the docs reflect resolved vs blocked.
- The stack reaches a state where a live smoke test can be attempted (all self-owned inputs
  closed), or the residual external blockers are explicitly named as the only gate.

---

## TASK-INFRA-007 - Deploy release safety: deep backend health check + wired voice drain

**Parent:** EPIC-012
**Related decisions:** ADR-0038
**Depends on:** TASK-INFRA-002 (HAProxy), TASK-OPS-002 (rolling deploy)
**Classification:** V1 pilot deployment (release correctness)
**Status:** 📋 Open — ready to start
**Priority:** Medium
**Branch:** `task/TASK-INFRA-007-deploy-release-safety`
**Surfaced by:** Sprint 11 full adversarial code+doc review (2026-08-05) — HAProxy probes a
static endpoint and voice drain hooks are empty.

### Context

HAProxy backend health checks `/api/health`, which returns a static UP
(`HealthController.java:17-21`) and does **not** reflect Redis/DB degradation that would fail
`/actuator/health` (the endpoint Ansible already polls, `group_vars/backend.yml:8`). A backend
with its dependencies down therefore stays in rotation. Separately, the voice rolling deploy
sets `voice_lb_drain_cmd`/`voice_lb_enable_cmd` **empty** (`group_vars/voice.yml:56-57`), so a
bridge being recreated is not drained — only a 60s grace pause protects in-flight calls.

### Scope

- Point the HAProxy backend health check at `/actuator/health` (or a dependency-aware
  endpoint) so an unhealthy backend leaves rotation.
- Populate `voice_lb_drain_cmd`/`voice_lb_enable_cmd` using the HAProxy admin-socket
  commands documented in `deploy/haproxy/README.md` so a bridge is drained before recreate.
- Extend `qa-validate-haproxy.sh` / `qa-validate-ansible.sh` checks accordingly.

### Acceptance

- HAProxy backend health reflects real backend health (unhealthy backend removed from LB).
- Voice deploy drains the target bridge before recreate; QA scripts assert both.
- Live drain/health behaviour validated once LB-host access is available (deferred to
  TASK-INFRA-006 closure).

---

## TASK-OPS-007 - Centralized observability for the pilot (turn the telemetry on)

**Parent:** EPIC-012
**Related decisions:** ADR-0028, ADR-0038, ADR-0039
**Depends on:** TASK-OPS-002 (env templates), TASK-OBS-001 (OTLP exporters)
**Classification:** V1 pilot deployment (observability / SLO substantiation)
**Status:** 📋 Open — ready to start
**Priority:** High
**Branch:** `task/TASK-OPS-007-centralized-observability`
**Surfaced by:** Sprint 11 full adversarial code+doc review (2026-08-05) — the instrumentation
model is strong but **export is disabled** in prod, so no p95/p99 can be aggregated in the
pilot; any SLO claim is unsubstantiable.

### Context

OTLP export is hard-disabled in `roles/compose_tier/templates/backend.env.j2:37-40` and
`voice.env.j2:25-26`; backend trace sampling is 0.0. The `deploy/observability/` collector
stack is local opt-in only. Operators would have to `curl` per-node Micrometer endpoints with
no aggregation — insufficient for a latency SLO.

### Scope

- Add a minimal centralized collector to the pilot topology (OTLP endpoint + metric
  aggregation, e.g. an OpenTelemetry Collector → Prometheus/backend of choice).
- Enable OTLP export in the prod `.env` templates pointing at the collector; set a sane
  sampling ratio.
- Propagate W3C `traceparent` voice→backend so a call is one trace across tiers.

### Acceptance

- A backend + voice run exports traces/metrics to the collector; p50/p95/p99 by slice are
  visible in one place.
- Correlation id / traceparent links a voice turn to its backend spans.
- Docs (`deploy/observability/README.md`, deployment ref) describe the pilot pipeline.

---

## TASK-OPS-008 - Data resilience: Redis + Postgres backup/restore

**Parent:** EPIC-012
**Related decisions:** ADR-0008 (Redis sessions + Postgres events), ADR-0038
**Depends on:** TASK-BE-021 (Redis memory), TASK-OPS-003 (host prereqs)
**Classification:** V1 pilot deployment (data durability)
**Status:** 📋 Open — ready to start
**Priority:** Medium
**Branch:** `task/TASK-OPS-008-data-resilience`
**Surfaced by:** Sprint 11 full adversarial code+doc review (2026-08-05) — Postgres (`.102`)
and Redis (`.107`) are single-node SPOFs with **no backup/restore**; rollback covers app
images only.

### Context

The topology has one Postgres (KB + pgvector, `inventory/hosts.ini:19-20`) and one Redis
(conversation memory, `:7-8`) with no replica, no Sentinel, and no `pg_dump`/AOF procedure in
the repo. One VM loss = data loss + outage, and there is no restore runbook.

### Scope

- Redis: enable AOF (or scheduled RDB) on the `redis-data` volume + a backup job; document
  restore.
- Postgres: a scheduled `pg_dump` (or documented PITR) with off-host copy + a restore runbook
  that recreates the `vector` extension and re-syncs KB if needed.
- Add both procedures to `docs/operations/` and reference them from the first-deploy runbook.

### Acceptance

- Documented, tested backup + restore for Redis and Postgres (restore into a clean VM
  verified at least once).
- RPO/RTO stated for each; rollback runbook cross-links the data procedures.

### Notes

- HA (replica/Sentinel/cluster) is out of scope here — this ticket is durability, not
  zero-downtime. HA can be a later hardening if the pilot widens.
