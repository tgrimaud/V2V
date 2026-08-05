# ADR-0038 - Pilot deployment architecture for the eir-ai4cc-tst environment

- **Status:** Accepted (2026-08-03); embeddings placement and provider egress resolved in ADR-0039 (TASK-INFRA-003, 2026-08-04)
- **Deciders:** Product owner (Thomas Grimaud), architecture
- **Related:** ADR-0008 (Redis active sessions / Postgres durable data), ADR-0010
  (industrialization requires contracts, SLOs and observability), ADR-0028
  (backend observability), ADR-0029 (pilot latency criterion), ADR-0033 (WebRTC
  single live voice transport), `docs/architecture/infra-v1.md` (generic target topology)
- **Sprint:** Sprint 11 (remote deployment and release readiness)

## Context

The platform team provisioned a first remote environment, **eir-ai4cc-tst**
(Rocky Linux EL9, cloud-provisioner), to deploy the Voice Support Bot for an
operator pilot. It is the first environment beyond a developer laptop.

What actually runs today (`feat/restart-from-scratch`) is a **two-service** web
Voice2Voice stack:

- **Voice bridge** (`voice-agent/`, Python): `python -m web_voice.server`, binds
  `127.0.0.1:8090` by default, heavy deps (`pipecat-ai`, `aiortc`,
  `opencv-python`), WebRTC live path (ADR-0033), calls Gradium (STT/TTS, cloud)
  and the backend over HTTP.
- **Conversation backend** (`backend/`, Java, Spring Boot 3.4.1 / Java 17): port
  `8080`, single `application.yml` fully overridable by environment variables,
  RAG over `pgvector` (768 dim), guardrails, in-process conversation memory,
  Mistral (chat, cloud) and Ollama `nomic-embed-text` (embeddings).

Neither service has a build/deploy artifact today: there is no `Dockerfile`, no
`mvnw`, and no CI. The only infrastructure files are a local-dev
`docker-compose.yml` (Postgres + Ollama) and an opt-in observability stack under
`deploy/observability/`.

The provided environment (full inventory in
[`docs/operations/deployment-eir-ai4cc-tst.md`](../../operations/deployment-eir-ai4cc-tst.md)):

- Tenant subnet `192.168.0.0/24`, admin (`.mt.lan`) and prod (`.prod.lan`) exposure.
- **2 LB VMs** (`vlp-ai4cc-t01/t02`) running **HAProxy + Keepalived**, with two VIPs:
  `vip-ai4cc-voice-t01` (`.10`, Prodpriv, prod IP `10.195.59.39`) and
  `vip-ai4cc-backend-t01` (`.11`, internal only).
- **1 PostgreSQL 18 VM** (`vlb-ai4cc-t01`, `.102`) where Postgres runs as a
  **podman pod** (`podpg`); `pgvector` (`CREATE EXTENSION vector`) is available to install.
- **2 voice-bridge VMs** (`vla-ai4cc-t01/t02`, `.103/.104`) - bare VMs behind the voice VIP.
- **2 backend VMs** (`vla-ai4cc-t03/t04`, `.105/.106`) - bare VMs behind the backend VIP.
- **1 Redis VM** (`vlb-ai4cc-t02`, `.107`) - bare VM.
- SSH key access as `grimaud@<host>` then `sudo su -`.

We need a repeatable way to build, ship and run these two services on this
environment, plus a release/rollback process, without over-engineering a pilot.

## Decision

### 1. Packaging: Docker images, docker-compose per tier on the app VMs

Each service is built into an **OCI image** and run with **docker-compose** on
its VMs. This was chosen over podman/Quadlet and over native systemd services:
it gives reproducible builds, isolates the heavy Python native deps
(`opencv-python`, `aiortc`) from the host, and keeps a single, well-understood
run mechanism across both tiers. (Postgres itself stays a platform-managed
podman pod on `.102`; we do not repackage it.)

- Backend image: multi-stage, JDK 17 build stage running `mvn -q -DskipTests
  package` (or a checked-in build), slim JRE 17 runtime stage, non-root user,
  `HEALTHCHECK` on `/actuator/health`, all config via environment variables.
- Voice-bridge image: Python 3.x base with the system libs `opencv`/`av` need,
  `pip install -r requirements.txt`, non-root user, entrypoint
  `python -m web_voice.server --host 0.0.0.0 --port 8090`, `HEALTHCHECK` on `/`.

### 2. Topology and VIPs

- Voice VIP `.10` (Prodpriv, `10.195.59.39`) -> voice bridges `.103`/`.104:8090`.
  This is the only externally exposed entry point; it terminates TLS for
  HTTPS/WSS (WebRTC signaling and media negotiation, ADR-0033).
- Backend VIP `.11` (internal only) -> backends `.105`/`.106:8080`.
- Backends reach Postgres `.102:5432` (pod), Redis `.107`, the embeddings model
  (placement below), and Mistral (cloud).
- Health checks: HAProxy checks voice on `GET /` and backend on `GET /api/health`
  (both ungated). Ports are finalized in TASK-INFRA-002 (the platform-side `8080`
  VIP value is a placeholder).

### 3. Shared conversation state on Redis (activates ADR-0008)

With **two backend instances behind VIP `.11`**, the current in-process
`InMemoryConversationMemoryAdapter` breaks multi-turn conversations: consecutive
turns can land on different instances and lose history. Sprint 11 therefore
implements a **Redis-backed conversation memory adapter** (ADR-0008), selected by
`CONVERSATION_STORE=redis`, using the provided Redis VM `.107`. In-memory stays
the default for local/dev and tests.

### 4. CI/CD: GitHub Actions build/test/image + Ansible/SSH deploy

- **GitHub Actions** (repo `tgrimaud/V2V`) runs the test gates (`mvn test`,
  voice-agent `unittest` + `behave`), builds both images, and pushes them to a
  container registry with an immutable **version tag** (release tag / git SHA).
- **Ansible over SSH** deploys to the VMs: render the per-tier `.env` from
  secrets, `docker compose pull` + `up -d` on the target hosts, with voice
  **session draining** before restart. **Rollback = redeploy the previous image
  tag.** GitHub Actions never holds long-lived infrastructure state; Ansible is
  the single deploy mechanism.

### 5. Configuration and secrets

All configuration is environment-driven (already true in code). Ansible renders
`.env` files consumed by docker-compose from a secrets source (GitHub Actions
secrets and/or an Ansible vault). Required secrets: `MISTRAL_API_KEY`,
`GRADIUM_API_KEY`, `CONVERSATION_API_KEY`, `DB_URL`/DB credentials, Redis
connection. **`CONVERSATION_API_KEY` must be non-empty in any non-local
environment** (an empty key opens the protected endpoints - acceptable only on a
laptop, never on the tst VIPs).

### 6. Embeddings placement and provider egress (RESOLVED - ADR-0039)

Resolved by **ADR-0039** (TASK-INFRA-003): embeddings run on **Ollama
`nomic-embed-text` (768 dim) as a CPU sidecar co-located per backend VM** (option
a) - no `vector_store` recreation, no cloud egress for RAG. Mistral embeddings
(option b) rejected for the pilot. The only provider egress the pilot needs is
`api.mistral.ai:443` (chat), the Gradium API `:443` (STT/TTS) and the container
registry `:443` (image pulls); the confirmed allowlist/proxy remains a platform
input tracked in the deployment doc.

### 7. Observability

Keep the current defaults: structured stdout logs + `/actuator/metrics`
(Micrometer) on the backend, stderr JSON telemetry on the voice bridge, per
ADR-0028. OTLP export stays **opt-in and off by default**. The inventory has no
observability/collector host, so a full OTLP collector deployment is **out of
Sprint 11 scope** and tracked as a later observability ticket, consistent with
the ADR-0010 industrialization gate.

## Consequences

- Two new build artifacts enter the repo (`backend/Dockerfile`,
  `voice-agent/Dockerfile`) plus per-tier compose files and Ansible playbooks
  under `deploy/`.
- A real code change lands in the backend (Redis-backed memory) so the two-
  instance topology is correct rather than best-effort.
- The release process becomes reproducible and auditable (versioned images,
  tag-based rollback), a prerequisite for the ADR-0010 industrialization path.
- The pilot can run on tst before billing/identity work, which is intentionally
  deferred (Sprint 12).
- Remaining risk is concentrated in the open inputs (egress, embeddings, TLS,
  registry, SSH source ranges) - all captured as explicit questions in the
  environment doc and gated behind TASK-INFRA-003 / TASK-INFRA-002 rather than
  guessed.

## Alternatives considered

- **Podman + Quadlet (systemd-managed containers).** Consistent with the
  platform's Postgres pod and rootless-friendly, but the operator chose Docker +
  compose on the app VMs for a single, familiar run mechanism. Revisit if the
  platform standardizes on podman.
- **Native systemd services** (`java -jar`, venv `python -m web_voice.server`).
  Lowest image overhead, but loses dependency isolation for the heavy Python
  native stack and reproducibility of the runtime; rejected.
- **Kubernetes** (as sketched in `infra-v1.md`). The recommended long-term
  operator target, but this tst environment is bare VMs + HAProxy, not a cluster;
  K8s stays the aspirational evolution, not the pilot deployment.
- **A message broker for backend<->voice communication.** Out of scope here and
  already rejected for the live path in ADR-0036.
