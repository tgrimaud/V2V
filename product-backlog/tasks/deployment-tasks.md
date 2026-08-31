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
- Keep the **internal** backend frontend (`.11:80`, LB→backend only) unrate-limited.
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
**Status:** ✅ Implemented (2026-08-06, branch `task/TASK-OPS-006-pin-actions-sha`) — all 8
third-party `uses:` in `tests.yml` + `images.yml` repinned to full commit SHAs (with a
trailing `# vX.Y.Z` readability comment), resolved live via `git ls-remote` (identical to the
commit each floating major tag pointed to, so no behaviour change): `actions/checkout` v4.4.0,
`actions/setup-java` v4.9.1, `actions/setup-python` v5.6.0, `docker/metadata-action` v5.10.0,
`docker/setup-buildx-action` v3.12.0, `docker/login-action` v3.7.0, `docker/build-push-action`
v6.19.2. Added `.github/dependabot.yml` (weekly `github-actions` ecosystem, grouped
actions/docker PRs, `ci` commit prefix) so SHAs are bumped by reviewed PRs. The local reusable
`uses: ./.github/workflows/tests.yml` is intentionally exempt (same-repo ref). QA:
`.github/qa-validate-workflows.sh` **27/27** (+3 new: SHA-pin, `# vX.Y.Z` comment guard,
Dependabot presence/YAML) and `actionlint` clean. **Not runtime-affecting** (CI-only; no app
code, no new latency slice → no OpenTelemetry change). Pending review/merge on user request.
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
**Status:** ✅ Implemented (2026-08-05, branch `task/TASK-INFRA-006-close-deploy-open-inputs`) —
closed every self-owned input and named the residual platform-owned gates. Own-able parts
delivered: (1) an **owner + status + gate tracker** for all 12 open inputs in
`deployment-eir-ai4cc-tst.md`, mirrored in `first-deploy-runbook.md` (step 0 + step 8);
(2) the **HAProxy/Keepalived manual apply path** in `deploy/haproxy/README.md` (packages →
`ip_nonlocal_bind` → configs → substitute NIC/VRID/VRRP-secret → cert → validate → enable →
failover test) + explicit VRRP-secret-from-vault handling (8-char truncation caveat);
(3) **STUN/TURN wiring**: runtime `build_ice_servers()` promotes TURN to credentialed
`IceServer`s (`VOICE_TURN`/`VOICE_TURN_USERNAME`/`VOICE_TURN_CREDENTIAL`, credential from
`vault_turn_credential`), wired group_vars → template → compose → container; also fixed a
stale "space-separated" STUN comment (code splits on commas). QA: voice-agent 468 unittest
(+4 `build_ice_servers`) + 169 behave, `qa-validate-ansible.sh` 62/62 (+4 TURN wiring),
`qa-validate-haproxy.sh` 33/33, `git diff --check` clean. Residual gates are platform-owned
(TLS cert+FQDN #4, SSH/ingress CIDR #1a, Prod→VIP NAT #11, TURN relay+creds #12, LB
apply/NIC/VRID/secret #10) and explicitly named — the stack is code-complete for a live
smoke test. Runtime-affecting: adds ICE-server env parsing (no new latency slice).
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
**Status:** ✅ Implemented (2026-08-05, branch `task/TASK-INFRA-007-deploy-release-safety`) —
HAProxy `backend_java` now probes the deep `/actuator/health` (DB + Redis-when-enabled,
503 on degradation) instead of the static `/api/health`; the voice drain/enable hooks are
wired to the HAProxy admin socket (`socat … /run/haproxy/admin.sock`, `state drain`/`ready`)
and delegated to every LB node (`voice_lb_socket_hosts`, either may hold the VIP). QA:
`qa-validate-haproxy.sh` 33/33 (incl. real `haproxy -c` + "no static `/api/health`" regression)
and `qa-validate-ansible.sh` 41/41 (incl. syntax-check + drain-wiring assertions). Live
drain/health behaviour deferred to TASK-INFRA-006 (LB-host SSH access). Runtime-affecting:
deploy/health config only, no application code change.
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

## TASK-INFRA-008 - Adapt the pilot deployment to the podman container runtime (Option B)

**Parent:** EPIC-012
**Related decisions:** ADR-0038 (addendum 2026-08-13, container runtime = podman)
**Depends on:** TASK-OPS-003 (host prereqs), TASK-OPS-002 (compose deploy), TASK-INFRA-006 (SSH access)
**Classification:** V1 pilot deployment (runtime alignment)
**Status:** ✅ Implemented (2026-08-13, branch `feat/sprint-11-remote-deployment`) — the deploy
no longer installs Docker CE. `host_prereqs` now ensures **podman + the `podman-docker` shim**
(both already shipped on the Rocky EL9 VMs), installs the **Docker Compose v2 binary as
podman's compose provider** (`compose_provider_*` vars, overridable to an internal mirror),
writes `/etc/containers/containers.conf` (`compose_providers` + `compose_warning_logs=false`)
and `/etc/containers/nodocker`, and enables the rootful `podman.socket` (Docker-compatible API
for the provider). `compose_cmd` flips to **`podman compose`**; `compose_tier` uses
`podman login`/`podman logout` (credentials land in `/run/containers/0/auth.json`, dropped
after the pull). The backend KB `:ro` bind mount is relabelled **`:ro,Z`** (SELinux Enforcing
on EL9 — mandatory under podman, backward-compatible with docker). `docker exec/run/inspect/cp`
in `health.yml` and the backup scripts keep working through the shim. Runtime-affecting: deploy
tooling only, no application code change.
**Live validation (2026-08-14):** `prereqs.yml --limit 'redis:backend'` applied on
`vlb-ai4cc-t02` + `vla-ai4cc-t03/t04` — `ok=9 changed=5 failed=0`, then idempotent
(`changed=0`); `podman compose version` = **v5.4.0** (provider checksum verified),
`podman.socket` **active**, `/etc/containers/containers.conf` rendered; firewalld tasks
skipped (firewalld inactive on the VMs). Control-node `ansible.cfg` `stdout_callback`
updated (the `community.general.yaml` callback was removed in v12 → `default` +
`result_format=yaml`).
**Priority:** High (blocks first-deploy Steps 3, 5, 6, 7)
**Branch:** `feat/sprint-11-remote-deployment`
**Surfaced by:** Step 0 first-deploy access (2026-08-13) — every app VM runs **podman 5.8.2**
with the `podman-docker` shim, **no Docker CE**, **no compose provider** (`podman compose`
fails "looking up compose provider"), `podman.socket` **disabled**, and SELinux **Enforcing**.
ADR-0038 §1 had chosen Docker + compose and explicitly said "Revisit if the platform
standardizes on podman"; it has.

### Context

ADR-0038 assumed Docker CE + the compose v2 plugin, and `prereqs.yml`/`host_prereqs` installed
`docker-ce`/`docker-compose-plugin` from the Docker repo. The provisioned VMs instead ship
podman 5.8.2 (rootless-capable, `wheel`/sudo for rootful) with only the docker CLI shim, and
neither `docker-compose-plugin` (no Docker repo) nor a compose provider is present. Installing
Docker CE would fight the platform's standard runtime and its Postgres podman pod on `.102`.

### Scope

- `host_prereqs`: stop installing Docker CE; ensure `podman` + `podman-docker`; install a
  Compose v2 provider binary (pinned version + checksum, URL overridable for an internal
  mirror); render `/etc/containers/containers.conf` (`[engine] compose_providers`,
  `compose_warning_logs=false`) + `/etc/containers/nodocker`; enable rootful `podman.socket`;
  verify `podman --version` + `podman compose version`.
- `compose_cmd: "podman compose"`; `compose_tier` login/logout via `podman`.
- Relabel the backend KB bind mount `:ro` → `:ro,Z` for SELinux Enforcing.
- Update ADR-0038 (addendum), the first-deploy runbook (Step 3), the deployment reference and
  backup-restore doc (shim reliance).

### Acceptance

- `prereqs.yml` on a fresh VM leaves `podman compose version` working and `podman.socket`
  active, with no Docker CE installed.
- `deploy.yml` per tier pulls + brings up each stack via `podman compose` and passes the
  existing health gates; the backend reads the `:ro,Z` KB mount without an SELinux AVC.
- Backup/restore scripts still run (through the `podman-docker` shim).
- Live validation folded into the first-deploy tier-A smoke (TASK-INFRA-006 access window).

---

## TASK-INFRA-009 - Manage the Postgres schema with Liquibase (versioned bootstrap)

**Parent:** EPIC-012
**Related decisions:** ADR-0041 (Liquibase schema management + bootstrap boundary), ADR-0038 (§ schema init superseded), ADR-0039 (pgvector/embeddings)
**Depends on:** TASK-INFRA-008 (podman runtime), TASK-OPS-008 (Postgres on `.102`), TASK-BE-003 (pgvector store), TASK-BE-021 (JPA ledger)
**Classification:** V1 pilot deployment + backend persistence
**Status:** In progress (branch `feat/sprint-11-remote-deployment`)
**Priority:** High (blocks first-deploy Step 4 → Steps 6)
**Branch:** `feat/sprint-11-remote-deployment`
**Surfaced by:** First-deploy Step 4 review (2026-08-14) — the schema was created implicitly by
Hibernate `ddl-auto: update` + Spring AI `initialize-schema: true`, and the privileged bootstrap
was ad-hoc superuser SQL in the runbook. Neither is versioned/reproducible; the user asked to
manage the Postgres bootstrap through Liquibase YAML shipped in the backend project.

### Context

The backend had no migration tool. `vector_store` (768-dim, HNSW cosine) was created by Spring AI's
`initialize-schema` (which also ran `CREATE EXTENSION vector`/`uuid-ossp` — **superuser-only**, fine
in dev where the app user is superuser, impossible on the pilot's Patroni where the app user is
unprivileged) and `kb_source_state` by Hibernate `ddl-auto: update`. On the pilot this forced a
manual superuser SQL step (`CREATE DATABASE`/`ROLE`/`EXTENSION`/`GRANT`) with no change tracking.

Liquibase connects **into** a database **as the app user**, so three operations can never be done
by app-startup Liquibase and must precede it: `CREATE DATABASE` (cannot create the DB it connects
to; non-transactional), `CREATE ROLE …LOGIN` (the app connects **as** that role → must pre-exist),
`CREATE EXTENSION vector`/`uuid-ossp` (superuser-only; the pilot app user is not superuser).

### Decision (split, ADR-0041)

- **App schema → Liquibase at startup (app user):** the backend owns `vector_store` (reproducing
  Spring AI 1.0.0's exact DDL byte-for-byte: `id uuid DEFAULT uuid_generate_v4() PRIMARY KEY,
  content text, metadata json, embedding vector(768)` + `spring_ai_vector_index` HNSW
  `vector_cosine_ops`) and `kb_source_state`, guarded by `preConditions … not tableExists` /
  `onFail: MARK_RAN` (no-op on legacy dev DBs already created by Spring AI). `ddl-auto: none`,
  `initialize-schema: false`.
- **Privileged bootstrap → a superuser Liquibase changelog (own tracking tables), run once at
  Step 4** via a one-shot `podman run liquibase/liquibase` container on the data VM toward the
  Patroni primary: `CREATE EXTENSION vector` + `uuid-ossp` + a defensive `GRANT` to the app user.
- **Irreducible psql pre-step:** only `CREATE DATABASE voicesupport`, `CREATE ROLE voicesupport
  LOGIN PASSWORD …`, `ALTER DATABASE … OWNER TO voicesupport` (secret `vault_db_password` stays
  out of every Liquibase file — chosen boundary).
- **Local dev:** the pgvector container creates `vector` + `uuid-ossp` via an init script
  (`scripts/dev-db-init/`), replacing the extension creation Spring AI used to do.

### Scope

- Backend: add `liquibase-core` (BOM-managed); `db/changelog/db.changelog-master.yaml` +
  `changes/001-vector-store.yaml` + `changes/002-kb-source-state.yaml`; bootstrap changelog
  `db/changelog/bootstrap/db.changelog-bootstrap.yaml`; flip `ddl-auto`/`initialize-schema`; wire
  `spring.liquibase`.
- Dev: `scripts/dev-db-init/01-extensions.sql` mounted in `docker-compose.yml`.
- Deploy/docs: rewrite runbook Step 4 (psql pre-step + one-shot Liquibase container), update the
  deployment reference, ADR-0038 cross-ref, CLAUDE.md storage note.
- Tests: changelog well-formedness + schema-parity assertions; `mvn test` regression (new dep).

### Acceptance

- `mvn test` green (offline; no `@SpringBootTest` boots the context, so Liquibase is inert in test).
- On a fresh app DB, backend startup runs the app changelog and creates `vector_store` (identical
  to Spring AI's schema) + `kb_source_state`; on a legacy dev DB the changesets MARK_RAN (no clash).
- Step 4 bootstrap changelog creates the extensions with its own tracking tables; the app user
  (DB owner) then creates the schema without superuser rights.
- The app-user password never appears in any Liquibase changelog/property.

---

## TASK-OPS-007 - Centralized observability for the pilot (turn the telemetry on)

**Parent:** EPIC-012
**Related decisions:** ADR-0028, ADR-0038, ADR-0039
**Depends on:** TASK-OPS-002 (env templates), TASK-OBS-001 (OTLP exporters)
**Classification:** V1 pilot deployment (observability / SLO substantiation)
**Status:** ✅ Implemented (2026-08-05, branch `task/TASK-OPS-007-centralized-observability`) —
Centralized pilot pipeline + W3C `traceparent` end to end, additive over the default-off
posture. (1) `deploy/observability/docker-compose.otel.yml` now also runs **Prometheus**
(scrapes the collector's `:8889` exporter, 15d retention) with `prometheus.yml`, so slice
percentiles (`voice_support_slice_*` p50/p95/p99 by slice/channel/provider/outcome) aggregate
in one queryable place. (2) One Ansible variable `otel_collector_endpoint` (empty ⇒ OFF)
drives both `backend.env.j2` + `voice.env.j2`: backend derives `/v1/metrics` + `/v1/traces`
and flips `OTEL_METRICS_EXPORT_ENABLED`/`OTEL_TRACES_SAMPLER_ARG` (`otel_traces_sampler_arg`,
default `1.0`); voice sets `OTEL_EXPORTER_OTLP_ENDPOINT`. (3) `voice_common/trace_context.py`
derives a deterministic W3C `traceparent` (BLAKE2b) from the turn's `correlation_id`;
`http_backend` injects it (`00-<trace>-<span>-01`, sampled), the backend continues the same
trace id (default W3C propagation + ParentBased sampler), and `otel_export` opens the
`voice.turn` root span under the same derived context → a voice turn and its backend spans
are one trace. Export stays async/best-effort (a down collector never blocks a turn). ADR-0028
addendum added. QA: voice-agent 476 unittest (+8: `test_trace_context.py`, export trace-id,
http_backend traceparent) + 169 behave; `qa-validate-ansible.sh` 69/69 (+7: OTEL OFF/ON render
+ collector/Prometheus wiring); `qa-validate-haproxy.sh` 33/33; `git diff --check` clean. Live
capture on the tst collector deferred to the access window (collector host = open input #13).
Runtime-affecting: voice HTTP header + export path (instrumentation only, additive).
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
**Status:** ✅ Implemented (2026-08-05, branch `task/TASK-OPS-008-data-resilience`) —
Redis AOF was already on (`--appendonly yes`); added an off-host-capable snapshot job
(`deploy/backup/redis-backup.sh` BGSAVE + AOF tar) and a Postgres `pg_dump -Fc` job
(`pg-backup.sh`, throwaway `postgres:16-alpine` client, one backend node) plus restore
scripts (`redis-restore.sh`, `pg-restore.sh` recreating the `vector` extension + KB
re-sync fallback). Ansible `compose_tier` role installs the scripts, renders `0600`
`no_log` env files (secrets from vault, never the crontab), and schedules hourly/daily
cron. New runbook `docs/operations/backup-restore.md` (RPO/RTO) cross-linked from the
first-deploy + release-process docs. QA: `qa-validate-ansible.sh` 47/47 (incl. `bash -n`
on all four scripts + credential-hygiene + one-node pinning). Live restore-into-clean-VM
drill deferred to the TASK-INFRA-006 access window. Runtime-affecting: deploy tooling +
schedule only, no application code change.
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

---

## TASK-INFRA-010 - HAProxy `wss` upgrade routing for the external WebSocket voice path

**Parent:** EPIC-006
**Related decisions:** ADR-0043 (interim WebSocket audio transport), ADR-0042 (no TURN),
ADR-0038 (pilot deployment), TASK-INFRA-002 (voice VIP `.10` TLS edge)
**Depends on:** TASK-WEB-026 (framing/socle), TASK-INFRA-002 (existing voice VIP)
**Classification:** V1 pilot deployment (edge wiring — carried to Sprint 13)
**Status:** ❌ **Superseded / dropped (2026-08-26, [ADR-0047](../../docs/architecture/adrs/ADR-0047-single-async-http-websocket-server-one-port.md)).** User decision: take the path that avoids touching the HAProxy config. Rather than a dedicated `voice_ws` `Upgrade` route + separate `:8091` backend at the edge, the runtime unifies HTTP + the WebSocket on **one routed port** (TASK-WEB-038), so HAProxy `mode http` tunnels the upgrade on the existing `voice_bridges` backend via the global `timeout tunnel` — no ACL, no second backend, no LB change, no platform-team dependency. The interim `voice_ws` reference config that TASK-WEB-037 had added was reverted. **No edge work remains under this ID**; the single-routed-port confirmation lives in TASK-WEB-038. Kept for traceability.
**Priority:** ~~Medium~~ (closed as superseded)
**Branch:** n/a (never started; superseded before implementation)

### Context

The interim WebSocket audio path (ADR-0043) reaches an off-subnet browser as one long-lived
`wss` connection through the existing voice VIP `.10` TLS edge (HAProxy, TASK-INFRA-002) —
the same edge that already terminates the WebRTC signalling and the batch HTTP path. No
TURN is provisioned (ADR-0042); media rides inside this TCP/TLS connection. HAProxy must
handle the WebSocket `Upgrade` and keep the long-lived connection alive for the length of a
call, and (since all sessions share one asyncio loop per bridge) keep a call pinned to one
bridge.

### Scope

- Route the WebSocket voice endpoint through the voice VIP with `Connection: Upgrade`
  handling (HTTP/1.1 at the edge, consistent with BUG-012's HTTP/1.1 decision).
- Long-lived timeouts for the `wss` connection (tunnel/`timeout tunnel`) so a call is not
  cut mid-conversation; keep the per-IP rate limiting (TASK-INFRA-004) at the edge.
- Session affinity so a call's frames stay on the bridge that owns its asyncio session.
- Update `deploy/haproxy/` config + README and the voice `.env` / Ansible `voice.env.j2`
  wiring; keep `VOICE_STUN`/`VOICE_TURN` empty (no TURN).

### Acceptance

```gherkin
Scenario: A wss voice connection survives a full call through the edge
  Given HAProxy configured for the WebSocket voice endpoint on the voice VIP
  When a browser opens a wss voice connection and holds a multi-turn conversation
  Then the Upgrade succeeds and the connection stays open for the whole call
  And the call's frames stay pinned to a single bridge
```

### Notes

- `qa-validate-haproxy.sh` must stay green (incl. real `haproxy -c`); add a check for the
  WebSocket route + tunnel timeout.
- No TURN, no STUN — this is the whole point of the interim path (ADR-0042/0043).

---

## TASK-INFRA-011 - Voice deploy health gate: probe the container health verdict, not host loopback

**Parent:** EPIC-012 (Pilot deployment, release & operations)
**Related decisions:** ADR-0038 (deploy topology), TASK-OPS-002 (Ansible deploy), TASK-OPS-004 (firewalld source-scoping)
**Depends on:** —
**Classification:** V1 pilot deployment — deploy-tooling fix (non-runtime)
**Status:** ✅ Implemented + validated live on t01/t02 (2026-08-26) on `task/TASK-INFRA-011-voice-health-container-probe` (off `feat/restart-from-scratch`). Surfaced during the **v0.6.0 deploy**: the voice rolling deploy hung ~15 min on the health gate and had to be finished with a per-host `-e health_url` override.

### Context

The Ansible deploy health task (`roles/compose_tier/tasks/health.yml`) probed each tier
over HTTP from the **host** with `ansible.builtin.uri` at `health_url`. For the **voice
bridge** this is `http://127.0.0.1:8090/`, which is a recurring false-negative (documented
in CLAUDE.md): the published port answers on the **192.168.x service IP** but returns **000
on host loopback**, and the management-interface FQDN is **firewalld source-scoped**
(TASK-OPS-004) so a probe there **hangs** (30 retries × ~30 s `uri` timeout ≈ 15 min) before
aborting the rolling deploy (`serial:1` + `max_fail_percentage:0`). During the v0.6.0 deploy
this blocked the voice tier; t02 had to be finished manually with
`-e health_url=http://192.168.0.104:8090/`.

### What was implemented

- Added a **container-health probe** to `health.yml`: when `health_container_name` is set,
  poll `docker inspect --format {{.State.Health.Status}} <name>` until `healthy`
  (30×5 s). The container's own `HEALTHCHECK` curls `localhost:8090` **inside the container
  namespace**, so it is immune to host interface/firewall/loopback quirks.
- `group_vars/voice.yml` sets `health_container_name: voice-support-bridge`; the HTTP `uri`
  probe is kept as a **fallback** (runs only when `health_container_name` is unset, e.g. the
  backend tier whose loopback `:8080` probe works) so the QA contract (`ansible.builtin.uri`
  present) is preserved.
- `qa-validate-ansible.sh` gains 3 assertions (container-health probe present + gated +
  voice tier uses it).

### Acceptance (met)

- `ansible-playbook deploy.yml --syntax-check` clean; `qa-validate-ansible.sh` **72/72** (+3).
- **Live**: re-running the voice deploy on t01/t02 with the committed config passes
  `Wait for voice container to report healthy (voice-support-bridge)` immediately and
  **skips** the loopback HTTP probe — no override, no hang, `failed=0`.

### Notes

- Non-runtime (deploy tooling only). Backend/redis health paths unchanged.
- Removes the need for the manual `-e health_url=<service-IP>` workaround on future voice deploys.

---

## TASK-OPS-009 - Deploy must trigger/verify KB sync + FR corpus default

**Parent:** EPIC-012 (Pilot deployment, release & operations) / EPIC-005 (answer engine)
**Related decisions:** ADR-0048 (bilingual KB corpus + retrieval language scope),
ADR-0038 (pilot deploy), ADR-0031 (answer language), ADR-0034 (audience filter)
**Related:** TASK-OPS-002 (Ansible deploy), TASK-BE-013/014 (CSV connector), TASK-BE-034
(retrieval language filter — target)
**Depends on:** TASK-OPS-002
**Classification:** V1 pilot deployment (release correctness + KB content)
**Status:** 🔧 Implemented on `task/TASK-OPS-009-kb-sync-fr-default` (2026-08-27, off
`feat/sprint-12-external-voice-websocket`): durable Ansible change (FR corpus default +
**async** post-deploy sync + `SyncReport.processed` gate) landed; `qa-validate-ansible.sh`
**76/76** (added 7 checks), YAML + playbook syntax-check clean. The immediate pilot load
(Part B step 1) was performed operationally out-of-band (see done-tasks 2026-08-27).
**Adversarial review 96/100 (Pass, 2026-08-27)** — contracts verified against backend source
(`SyncReport.processed = documents.size()` → an idempotent re-deploy still passes the gate;
`x-api-key` gate on `/api/knowledge/**` + `/retrieve`; global `SNAKE_CASE` Jackson so the
`top_k` body + `json.*` reads resolve). Two non-blocking maintainability findings fixed
(dropped `no_log` on the `async_status` wait so a failed sync is diagnosable; read-only
retrieval smoke-check marked `changed_when: false`); `qa-validate-ansible.sh` re-run **76/76**.
Report: [`docs/qa/task-ops-009-kb-sync-fr-default-adversarial-review.md`](../../docs/qa/task-ops-009-kb-sync-fr-default-adversarial-review.md).
Pending user validation / merge.
**Priority:** High
**Branch:** `task/TASK-OPS-009-kb-sync-fr-default`

### Problem

Two gaps made the live pilot RAG **markdown-only** (39 chunks, 3 FR FAQ files) with **zero
CSV content**, so mobile/support questions such as *"j'ai un problème avec mon téléphone
mobile"* had no grounded evidence and deflected to an advisor (DEC-002):

1. **The Ansible deploy copies KB assets but never syncs them.**
   `roles/compose_tier/tasks/kb_assets.yml` drops `knowledge-base/*.md` + the CSV corpus
   under `KB_HOST_PATH`, but **no task triggers `POST /api/knowledge/sync`** — the initial
   markdown sync was run manually once, and no CSV was ever synced. A redeploy therefore
   leaves the RAG empty/markdown-only unless someone remembers the manual step.
2. **The CSV default was the English `articles.csv`.** Pilot users are French; FR-on-FR
   retrieval grounds far better than FR-on-EN (ADR-0048).

### Objective

Make a (re)deploy self-sufficient: copy the **French** corpus, tag it `fr`, and **trigger +
verify** the KB sync post-deploy so the RAG is never left empty/markdown-only.

### Scope (delivered)

- **FR corpus default** (group_vars/backend.yml): `kb_csv_filename: "articles-fr.csv"` +
  `kb_csv_language: "fr"`; `kb_assets.yml` copies `{{ kb_csv_filename }}`; `backend.env.j2`
  renders `KB_CSV_PATH=/app/kb-assets/{{ kb_csv_filename }}` + `KB_CSV_LANGUAGE={{ kb_csv_language }}`;
  `.env.example` mirrors it.
- **Post-deploy sync** (new `roles/compose_tier/tasks/kb_sync.yml`, backend tier only, after
  `health.yml`, gated `kb_sync_after_deploy`): reads `CONVERSATION_API_KEY` from the rendered
  `.env` (`no_log`, never on argv), then fires `POST /api/knowledge/sync` **async** (`poll: 0`)
  and waits via `async_status` (90 × 30 s = 45 min headroom). **Why async:** the first CSV sync
  is slow — ~300 articles are embedded on the co-located CPU Ollama sidecar AND each is
  domain-classified by an embedding call at parse time (ADR-0030), so a full run takes ~15–30 min
  on the pilot, far past any single-request timeout (a naïve 600 s `uri` call would time out and
  fail the deploy). **Deploy gate:** assert the aggregate `SyncReport.processed >=
  kb_sync_min_processed` (default 50; markdown baseline is 3, the FR corpus adds ~300) — this
  proves the CSV corpus was actually seen/parsed, so the RAG is never silently left markdown-only.
  We gate on `processed` (not `ingested`) because an idempotent re-deploy skips unchanged sources
  (`ingested=0`) yet is a success. A `POST /api/conversation/retrieve` call then smoke-checks the
  pipeline (gated on HTTP 200 + evidence count logged) — deliberately **not** the CSV-loaded gate,
  since the always-present markdown FAQ can satisfy retrieval and the fail-closed audience filter
  (ADR-0034) legitimately returns 0 chunks for a query with no customer-facing match.
- **QA:** `qa-validate-ansible.sh` extended (76/76) — FR default, env wiring, sync wired +
  verifies, api-key `no_log`, **async + async_status**, **`processed` gate**.

### Acceptance

```gherkin
Scenario: A redeploy leaves the RAG populated, not markdown-only
  Given the backend stack is (re)deployed via Ansible
  When the post-deploy step runs
  Then POST /api/knowledge/sync is fired async with the api key read from the rendered .env
    And the play waits for the sync to finish via async_status (no single-request timeout)
    And the deploy fails if SyncReport.processed is below the CSV baseline (markdown-only)

Scenario: An idempotent re-deploy is a fast no-op
  Given the CSV corpus is already synced (unchanged content_hash)
  When the post-deploy sync runs again
  Then it skips unchanged sources (ingested=0) and still passes the processed gate

Scenario: The pilot CSV corpus is French
  Then KB_CSV_PATH points at articles-fr.csv and KB_CSV_LANGUAGE is fr
```

### Residuals / notes

- **Language tag on the interim operational load (ADR-0048):** the immediate pilot load (Part
  B step 1) dropped `articles-fr.csv` at the already-mounted `articles.csv` path and synced
  `csv-article` while `KB_CSV_LANGUAGE` was still `en`, so those chunks carry a cosmetic
  `language=en`. Harmless today (no language filter; answer language per-request). Once
  **TASK-BE-034** lands, a **forced re-sync** is needed to re-tag `fr` (idempotent sync skips
  on identical content_hash). A clean redeploy with this ticket's config tags correctly from
  the start (source_type stays `csv-article`, language `fr`).
- **Do NOT run a full prod redeploy** solely for this unless clearly safe (known voice
  health-gate false-negative, TASK-INFRA-011). The operational pilot load (step 1) is the
  immediate fix; this ticket makes the next planned redeploy durable.
- **Bilingual target:** when TASK-BE-034 (retrieval language filter) lands, revisit to load
  both `csv-article` (EN) + `csv-article-fr` (FR).
- **Corpus is an internal back-office KB (audience boundary, ADR-0034):** the FR corpus is a
  translation of the Eir operator KB, dominated by agent/back-office procedures. The
  `KeywordAudienceClassifierAdapter` tags an article `internal` when its title/content matches a
  marker (`back office`, `vérification d'aptitude`, `r6/ion`, `vaa`, `vrd`), and the customer
  answer engine is **fail-closed to `audience=customer`**. Observed during the pilot sync: even
  *"Mobile : Guide de dépannage"* was tagged `internal` (its body references back-office steps),
  so it is excluded from customer retrieval. Consequence: loading the corpus does **not**
  guarantee the mobile question grounds — the customer-facing partition may be thin. This is a
  **KB-quality / audience-tuning** matter (curate the customer-facing FR partition), not a deploy
  defect — and **not** a branding issue: the Eir brand in the corpus is intentional and correct
  (the content is Eir's and the product's purpose is to answer Eir customer problems), so no
  rebrand is needed (the earlier TASK-BE-035 rebrand follow-up is cancelled). The pilot
  verification (done-tasks 2026-08-27) records the actual customer-retrieval outcome for the
  mobile query.
- **Sync is embedding-bound, not a fixed cost:** every article triggers a domain-classification
  embedding at parse time (ADR-0030) *before* the per-chunk storage embeddings, all on the CPU
  Ollama sidecar (`ollama_cpus: 1.0`). The vector store therefore stays at the markdown baseline
  until the whole parse phase completes, then CSV chunks appear per document. This is why the
  sync is fired async and gated on `SyncReport.processed`, and why `voice-support.embedding.timeout-ms`
  is raised to 120 s on the backend tier (`java_opts`) for the sync batch.

- Interim manual workaround (already documented): verify health out-of-band
  (`docker inspect --format {{.State.Health.Status}}` + `curl http://<host-ip>:8090/`), then
  finish a blocked node by bumping `IMAGE_TAG` in `/opt/voice-support/voice/.env` (preserve the
  vault-rendered secrets — never hand-write `.env`) and `podman compose up -d --remove-orphans`.

---

## TASK-INFRA-012 - Genesys Architect flow + control/routing plane (Call Audio Connector + advisor-queue routing + wss endpoint exposure)

**Parent:** EPIC-007 (Genesys advisor handoff) / EPIC-012 (pilot deployment)
**Related decisions:** ADR-0040 (control/routing plane owned by Architect + Platform API), ADR-0049
(Sprint 13 delivery shape), ADR-0020 (Genesys handoff), ADR-0047 (single async server hosts the `wss`
endpoint), ADR-0038 (pilot deployment / edge)
**Depends on:** TASK-WEB-025 (spike **GO** + pilot access), OQ-006 (pilot environment + queue routing
rules), TASK-WEB-041 (the `wss` endpoint the flow forks to)
**Classification:** V1 pilot deployment — Genesys control plane config (no business logic) + voice-runtime connection auth
**Status:** 🧪 Prep implemented on branch `task/TASK-INFRA-012-genesys-audiohook-auth` (off `feat/sprint-13-genesys-audio-connector`); AudioHook connection auth (API key + HMAC-SHA256 signature) + Architect flow control/routing contract scaffolded; exact header/secret + `@request-target`/`@authority` behind the edge + Architect wiring pending live Genesys measurement; awaiting adversarial review + user merge (not merged)
**Priority:** High (Sprint 13; co-developed with TASK-WEB-041) — closes part of **R3/R6**
**Branch:** `task/TASK-INFRA-012-genesys-audiohook-auth` (off the sprint branch)

### Context

ADR-0040 splits Genesys into three planes; the **control/routing plane** — call steering, transfer,
queue and advisor routing — is owned by **Genesys Architect + the Platform API**, not by our media
socket. This ticket stands up the Architect flow that forks the call to our Audio Connector `wss`
endpoint, pauses, then resumes and routes on session end, plus the endpoint exposure/TLS/auth. No
conversation logic lives here (that stays in the backend, ADR-0001).

> **Edge note (2026-08-27):** the earlier TASK-INFRA-010 (`voice_ws` HAProxy special-case) was
> **superseded by ADR-0047** — the runtime serves the WebSocket on the single routed port, so HAProxy
> `mode http` tunnels the upgrade on the existing `voice_bridges` backend with no LB change. The Audio
> Connector `wss` endpoint rides that same routed port; this ticket does **not** re-open an edge
> special-case, only the Genesys-side flow + endpoint exposure/auth.

### Scope

- **Architect flow** with the **Call Audio Connector** action: fork the call audio to our `wss`
  endpoint, pause the flow while streaming, resume when our runtime ends the session.
- **Advisor-queue routing on escalation/resume**: route to the billing advisor queue with the
  queue/skill rules from OQ-006, carrying the `handoff_id` + permitted identifiers (TASK-BE-036/037).
- **Fail-safe route** (pairs with TASK-WEB-044): if our endpoint is unreachable/times out, the flow
  routes straight to the advisor queue after a defined guard delay.
- **Endpoint exposure**: reachable `wss://` on the routed port through the existing TLS edge (ADR-0047,
  no new edge special-case), with the auth the Audio Connector requires; keep the per-IP edge limits.
- **Integration budget**: track the premium ≤5-Audio-Connector-integrations/org constraint against the
  pilot (R6).
- Config + reference flow export are **versioned under `deploy/`** (not merged into the runtime); no
  secrets in the repo.

### Acceptance

```gherkin
Scenario: A pilot call is forked to the bot and routed to an advisor on escalation
  Given an Architect flow with a Call Audio Connector action pointing at our wss endpoint
  When a pilot caller reaches the flow and the bot cannot resolve the billing question
  Then the flow forks audio to the bot, pauses, and resumes when the session ends
  And the caller is routed to the billing advisor queue with the handoff reference attached
Scenario: The flow fails safe when the bot endpoint is unavailable
  Given the Call Audio Connector endpoint is unreachable
  When a call reaches the flow
  Then the caller is routed straight to the advisor queue after the guard delay
```

- Architect flow forks/pauses/resumes correctly against the TASK-WEB-041 endpoint.
- Escalation resume routes to the advisor queue with the handoff reference (TASK-BE-036).
- Fail-safe route verified (pairs with TASK-WEB-044); premium integration budget recorded.
- Reference flow/config versioned under `deploy/`; no conversation logic in Genesys.

### Notes

- The Platform API / Architect specifics (variable names, queue ids, auth mechanism) are confirmed by
  the TASK-WEB-025 spike against the real pilot org (OQ-006); this ticket implements the confirmed shape.

### Increment (2026-08-28) — Prep: AudioHook connection auth + Architect flow contract

Deterministically-knowable half implemented now (the AudioHook connection-auth scheme is a known
protocol); anything needing the live Genesys tenant / negotiated shared secret is marked
`TODO(TASK-INFRA-012: live-measurement)`. **ADR-0001 held — voice-runtime + docs only, zero backend
files changed.**

- **Voice-runtime auth (new):** `voice-agent/web_voice/genesys_auth.py` (policy + fail-closed config +
  telemetry) and `voice-agent/web_voice/genesys_signature.py` (IETF HTTP Message Signatures
  canonicalization, `alg="hmac-sha256"`). Verifies `X-API-KEY` (constant-time) + the `Signature` /
  `Signature-Input` HMAC over the covered components, keyed by `GENESYS_AUDIOHOOK_SECRET` (base64), with
  `hmac.compare_digest`. Canonicalization is locked against the **official Genesys golden vector**
  (unit test reproduces the published signature byte-for-byte).
- **Wiring:** `genesys_app.py` verifies auth **before** the WS upgrade (401/503 on failure, no session
  built); `server.py` always attaches an env-built authenticator when `--genesys` is enabled and
  **fails closed** with a structured warning when key/secret are unconfigured. Origin allowlist kept as
  defense-in-depth.
- **Telemetry (mandatory):** bounded-cardinality auth-outcome event + metric on the Genesys channel
  (`accepted` / `rejected_bad_signature` / `rejected_missing_key` / `rejected_not_configured`),
  connection-scoped correlation (Genesys session id → deterministic traceparent when no conversationId
  yet). **No secret / signature / API key / PII in any span, metric or log** (asserted by test).
- **Contract doc (new):** `docs/integrations/genesys-architect-flow-contract.md` — the Architect
  control/routing plane: fork/pause/resume vocabulary, by-reference handoff (`escalation_context =
  {handoff_id, reason_code, priority}`) routed to the advisor queue via
  `GET /api/conversation/escalation-handoffs/{handoff_id}` (TASK-BE-036), fail-safe branch, and the
  TO-CONFIRM table (DID, queue, egress ranges, auth header casing, variable limits) with owners.
- **Tests:** `tests/test_genesys_auth.py` (17 unit) + `features/genesys_connection_auth.feature`
  (5 scenarios) — valid accepted, tampered/invalid rejected, missing key, fail-closed unconfigured,
  telemetry-without-leak. Full suite green: 677 unit / 18 features · 51 scenarios · 225 steps.
- **TODO(live-measurement) seams:** exact API-key header casing, the signed `@request-target` /
  `@authority` as seen behind the pilot HAProxy edge, the negotiated shared secret, and the org-id
  allowlist — all env-configurable so live values drop in without a code change.

### Increment (2026-08-28) — Adversarial-review remediation (80/100 → fixed 3 Majors + 2 minors)

The review scored the prep 80/100 (blocked). All findings addressed; still voice-runtime + docs
only (ADR-0001 held — zero backend files). Full suite green: **685 unit / 18 features · 51
scenarios · 225 steps**.

- **Major A (telemetry discarded in prod):** `server.py` now builds the authenticator with the
  REAL exporter — `genesys_authenticator_from_env(log=genesys_log_telemetry)` (stderr + OTLP, the
  same path the session handler uses) instead of the no-op default, so the mandatory per-attempt
  auth-outcome event/metric is actually flushed at runtime. New test injects a capturing exporter
  and asserts it RECEIVES the event + metric on BOTH an accepted and a rejected attempt.
- **Major B (replay/freshness ENFORCED):** new `voice-agent/web_voice/genesys_replay.py`
  (`signature_is_fresh` + bounded FIFO `NonceCache`). Policy now: `expires` is **mandatory**
  (absent/stale/future → rejected via the existing bad-signature outcome, no unbounded label);
  `created`, when present, is age-bounded to `GENESYS_AUDIOHOOK_MAX_SIGNATURE_AGE_S` (default
  **300s**, small clock skew) — repaired from the old logic that merely EXTENDED the `expires`
  grace; a reused `nonce` is rejected via a cap of `GENESYS_AUDIOHOOK_NONCE_CACHE_SIZE` (default
  **10000**). `created`/`nonce` stay OPTIONAL so the golden vector (far `expires`) stays
  byte-identical (clock anchored near its `created`); canonicalization untouched. Regression tests:
  missing `expires`, stale/future `created`, replayed `nonce`, fresh unique nonce accepted,
  created-absent accepted, golden still green.
- **Major C (unbounded-cardinality metric):** dropped `correlation_id` from `AUTH_OUTCOME_METRIC`
  (kept it on the event/span); the metric label set is now exactly `{channel, outcome}` (asserted).
- **Minor 1 (insecure default):** `make_genesys_handler` now REQUIRES `authenticator` (always
  authenticates) so a forgotten wiring fails CLOSED; production behaviour unchanged (server always
  passes one). Transport-only tests pass an explicit accept-all double.
- **Minor 2 (non-ASCII API key → 500):** API-key compare is now byte-based
  (`.encode("utf-8")`), so a non-ASCII `X-API-KEY` degrades to a clean 401 (`rejected_missing_key`),
  never a 500.
- **Module budget:** freshness/nonce extracted to `genesys_replay.py`; `genesys_auth.py` stays
  under the 200-non-blank-line budget (193). Env var renamed to the reviewed
  `GENESYS_AUDIOHOOK_MAX_SIGNATURE_AGE_S`.
- **Docs:** freshness/replay policy + remaining `TODO(TASK-INFRA-012: live-measurement)` added to
  `genesys_auth.py` docstring and `docs/integrations/genesys-architect-flow-contract.md`.

---

## TASK-OPS-010 - Bridge active-session `/drain` endpoint + deploy wiring

> **ID note:** Originally filed as **TASK-OPS-010** on the retired `fix/BUG-017-voice-turn-hang`
> branch. The id was verified **free** on the mainline (no other `TASK-OPS-010` exists across the
> active branches), so it is kept unchanged; only its BUG/WEB cross-references were renumbered
> (BUG-017 → BUG-018, TASK-WEB-037/038 → TASK-WEB-045/046) to match the ported tickets.

**Parent:** EPIC-012 (Pilot deployment, release & operations)
**Related decisions:** ADR-0038 (pilot deployment), ADR-0025 (native barge-in / audio drain the bridge already uses per-turn)
**Related:** BUG-018 (stuck-in-thinking incident — P1 fix #3), TASK-OPS-002 (Ansible session-draining hook, grace-only today), TASK-INFRA-007 (LB drain/enable via HAProxy admin socket — stops NEW calls, not live ones), TASK-INFRA-011 (known voice health-gate loopback false-negative), TASK-WEB-008 (per-turn audio `drain()`)
**Depends on:** TASK-OPS-002 (compose deploy + drain hook), TASK-INFRA-007 (LB drain wiring)
**Classification:** V1 pilot deployment (release correctness) + voice runtime
**Status:** 📋 Planned (P1, planning only — not implemented). Filed 2026-08-27 from the BUG-018 investigation.
**Priority:** High
**Branch:** `task/TASK-OPS-010-bridge-drain-endpoint` (to create when work starts)
**Surfaced by:** BUG-018 read-only investigation (2026-08-27) — a bridge recreate / deploy / HAProxy failover mid-turn can hard-cut a live call and strand the UI, because there is no active-session drain.

### Context

The voice bridge has **no active-session `/drain` endpoint** — this is a documented gap in
`deploy/ansible/group_vars/voice.yml` ("The bridge has no active-session endpoint yet, so
draining is best-effort … A hard 'wait until 0 active calls' still needs a bridge /drain
endpoint (follow-up)"). Today a redeploy relies on three best-effort levers only:
`serial: 1` (one bridge recreates at a time so the VIP peer keeps serving), the
TASK-INFRA-007 LB drain hook (stops **new** calls hitting the node via the HAProxy admin
socket), and a bounded `voice_drain_grace_seconds` grace window. None of these **wait for
in-flight calls to finish**, so a call still in progress when the grace window elapses is
hard-cut with no terminal signal — one of the ways BUG-018's "stuck in thinking" can occur
during a deploy/failover. Note: the existing `drain()` in `web_voice/streaming_runtime.py` /
`webrtc_signaling.py` (TASK-WEB-008 / ADR-0025) drains a **single turn's** TTS audio buffer;
it is **not** a session-level graceful-drain for deploys.

### Objective

Add a graceful active-session drain to the bridge and wire it into the Ansible voice deploy
so a bridge recreate/deploy/failover lets live calls wind down (bounded) instead of
hard-cutting them, replacing the grace-only ceiling documented in `group_vars/voice.yml`.

### Scope

- **Bridge:** an active-session drain capability (e.g. a control endpoint / signal) that
  stops accepting new sessions and reports when in-flight sessions have drained, so the
  deploy can wait for "0 active calls" up to a bounded timeout before recreate; on timeout,
  end remaining calls gracefully (emit the terminal control signal per TASK-WEB-046) rather
  than a silent hard-cut. Reuse the existing active-session accounting
  (`voice_max_webrtc_sessions` gauge / WS active-session gauge) rather than new state.
- **Deploy wiring:** call the bridge drain before recreate in the Ansible voice deploy
  (`roles/compose_tier`), superseding the grace-only path; keep it fail-safe (a drain
  failure degrades to today's grace behaviour, never aborts the whole play — consistent
  with the `voice_lb_socket_hosts` opt-in safety net).
- **Health-gate interaction:** account for the known voice HTTP health-gate loopback
  false-negative (TASK-INFRA-011) so the drain step does not compound a false abort during
  a rolling deploy; confirm health out-of-band as documented.
- **Docs:** update `deploy/ansible/group_vars/voice.yml` (remove the "no /drain endpoint
  yet" caveat), `docs/operations/release-process.md` and the first-deploy runbook.
- OpenTelemetry: record the drain outcome (sessions drained vs force-ended, elapsed) so a
  deploy that cut a live call is observable.

### Acceptance Criteria

```gherkin
Scenario: A redeploy during an active call drains rather than hard-cuts
  Given an active voice call on a bridge that is being recreated by the deploy
  When the voice deploy runs against that bridge
  Then the bridge stops accepting new sessions
    And the deploy waits for the in-flight call to finish (up to a bounded timeout)
    And the call is not hard-cut mid-turn before the container recreates

Scenario: Drain is fail-safe
  Given the bridge drain cannot complete (endpoint error or timeout exceeded)
  Then remaining calls are ended gracefully with a terminal signal
    And the deploy degrades to the grace-window behaviour without aborting the whole play
```

### Out Of Scope

- The backend/runtime wall-clock turn deadline (TASK-WEB-045) and the browser watchdog
  (TASK-WEB-046) — sibling BUG-018 P1 fixes.
- Repointing the health gate off loopback (TASK-INFRA-011) — only accounted for here, not
  fixed.

## TASK-INFRA-015 - Enable the Genesys AudioHook endpoint on the pilot voice bridge (config + secrets + rollout)

**Parent:** EPIC-007 (Voice runtime) / EPIC-012 (Pilot deployment, release & operations)
**Related decisions:** ADR-0047 (single async HTTP+WS server), ADR-0049 (Genesys Audio Connector delivery shape), DEC-012 (Genesys = pilot entry), DEC-014 (concurrency target 3)
**Depends on:** TASK-WEB-041 (Audio Connector transport adapter), TASK-INFRA-012 (Genesys AudioHook auth), TASK-WEB-047 (local test client / Step 0b self-test)
**Classification:** V1 pilot deployment — deploy config + secrets (activates runtime behaviour that already shipped in the image; no image change)
**Status:** 🧪 Implemented on `task/TASK-INFRA-015-genesys-endpoint-enablement` (off sprint-13). Enablement config committed; the AudioHook shared secret is generated by us and stored in the local git-ignored `vault.yml` for the pre-live self-test.

### Context

The Genesys Audio Connector code (TASK-WEB-041/042/043 + the connection-auth of
TASK-INFRA-012) ships **inside** the voice image, but the deployed bridge ran with the
endpoint **off**: `web_voice/server.py` reads `--genesys` from `VOICE_GENESYS` (default
`off`) and the deploy config passed **no** genesys env, so `/genesys/audiohook` returned
404 on the pilot (`vla-t01/t02`). Testing the deployed connector — even the pre-live
self-test (runbook Step 0b, TASK-WEB-047) — first requires **activating** the endpoint and
provisioning its HMAC connection-auth secret. Enabling it needs **no image rebuild**: it is
purely env + secret + a rollout of the (now genesys-capable) mainline image.

### What was implemented

- **Compose passthrough** (`deploy/compose/voice/docker-compose.yml` + `.env.example`):
  `VOICE_GENESYS` (default off), `GENESYS_AUDIOHOOK_API_KEY`, `GENESYS_AUDIOHOOK_SECRET`,
  `GENESYS_AUDIOHOOK_AUTHORITY` (optional edge override), `VOICE_GENESYS_ALLOWED_ORIGINS`,
  `VOICE_GENESYS_CODEC` (default L16), `VOICE_GENESYS_MAX_SESSIONS` (default 3).
- **Ansible render** (`roles/compose_tier/templates/voice.env.j2`): renders the above from
  `group_vars/voice.yml` (`voice_genesys: "on"`, `voice_genesys_codec: L16`,
  `voice_genesys_max_sessions: 3`, allowlist + authority defaults) and the vault secret.
- **Vault contract** (`group_vars/all/vault.example.yml`): documents
  `vault_genesys_audiohook_api_key` / `vault_genesys_audiohook_secret` (base64). The real
  pair is generated locally (`openssl rand -base64 32`) and lives in the git-ignored
  `vault.yml` — **our own secret for the self-test**, rotated to the Genesys-admin-agreed
  shared secret before the live-org test.
- **Additive, non-regressive**: `/genesys/audiohook` mounts on the SAME routed `:8090` as
  `/ws` (ADR-0047, `web_voice/app.py`); the browser WS + WebRTC routes are unchanged (only
  the standard container recreate applies at rollout, drained per `release-process.md`).

### Acceptance (met)

- `voice.env.j2` renders all `VOICE_GENESYS*` / `GENESYS_AUDIOHOOK_*` lines with no
  undefined-variable error (`ansible … -m template` render check).
- The AudioHook secret never appears on argv or in a committed file (vault-encrypted;
  `.env` is Ansible-rendered on the host, never committed).
- Post-rollout: `/genesys/audiohook` accepts a correctly-signed handshake from
  `genesys_local_client.py` over an SSH tunnel to the bridge LAN IP (Step 0b), while `/ws`
  keeps serving.

### Out Of Scope

- The Genesys-side Architect flow + org config + the admin-agreed shared secret
  (TASK-INFRA-012 Genesys side / runbook Steps 1-6).
- Genesys-path degraded modes (TASK-WEB-044, carried forward) and any ADR-0029 SLO claim
  (decoupled — DEC-015).
