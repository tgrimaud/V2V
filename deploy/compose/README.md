# Per-tier docker-compose deploy stacks (eir-ai4cc-tst)

Docker Compose stacks that run the two service images on the **eir-ai4cc-tst**
pilot VMs and wire them to Postgres, Redis and the cloud providers
(TASK-INFRA-001, [ADR-0038](../../docs/architecture/adrs/ADR-0038-pilot-deployment-architecture-eir-ai4cc-tst.md)).
Environment inventory and the full per-tier variable contract:
[`docs/operations/deployment-eir-ai4cc-tst.md`](../../docs/operations/deployment-eir-ai4cc-tst.md).

## Stacks and placement

| Stack | VMs | Image | Reaches |
|-------|-----|-------|---------|
| [`backend/`](backend/docker-compose.yml) | `vla-t03`/`t04` (`.105`/`.106`) | TASK-DEPLOY-001 backend | Postgres `.102`, Redis `.107`, embeddings host, Mistral (cloud) |
| [`voice/`](voice/docker-compose.yml) | `vla-t01`/`t02` (`.103`/`.104`) | TASK-DEPLOY-002 voice bridge | backend VIP `.11`, Gradium (cloud) |
| [`redis/`](redis/docker-compose.yml) | `vlb-t02` (`.107`) | `redis:7-alpine` | — (skip if the platform provides Redis natively) |

One instance runs per VM; the HAProxy/Keepalived VIPs load-balance each pair
(voice `.10`, backend `.11`) — that LB config is **out of scope here**
(TASK-INFRA-002).

## Usage (per VM)

```bash
cd deploy/compose/<tier>
cp .env.example .env      # Ansible renders the real .env from secrets (TASK-OPS-002)
# edit .env — never commit it
docker compose config     # validate the rendered stack
docker compose up -d
docker compose ps         # STATUS should reach "healthy"
```

Rollback = set `IMAGE_TAG` to the previous version and `docker compose up -d`
(full runbook in TASK-OPS-002).

## Conventions

- **Env-driven only.** Every value comes from the sibling `.env`; no secret is in
  the compose files or the images. `.env` is git-ignored — only `.env.example` is
  versioned.
- **Image reference** is `${*_IMAGE}:${IMAGE_TAG}` so the registry (open input #5)
  and the version are injected at deploy time, not hard-coded.
- **Healthchecks** mirror the image `HEALTHCHECK`s (backend `/actuator/health`,
  voice `GET /`, Redis authenticated `PING`) so `docker compose ps` reflects real
  readiness.
- **Resource limits** are sized to each VM flavor and `restart: unless-stopped`;
  logs use `json-file` with rotation (10 MB × 5).
- **API key parity:** the voice `VOICE_BACKEND_API_KEY` MUST equal the backend
  `CONVERSATION_API_KEY`; the backend and Redis `REDIS_PASSWORD` MUST match.
- **Knowledge base:** the backend image ships only the jar, so the KB assets are
  mounted read-only from `KB_HOST_PATH` (must contain `knowledge-base/` + `articles.csv`)
  and synced into pgvector on first run (`POST /api/knowledge/sync` or the scheduler).
  Alternative for full reproducibility: bundle the KB in the image (DEPLOY-001 follow-up).

## Depends on open inputs

These stacks are ready but need a few environment inputs to run end-to-end
(tracked in the deployment doc, gated by TASK-INFRA-002/003):

- Container **registry** path + credentials (open input #5) → `*_IMAGE`.
- **Embeddings** host placement (open input #3, TASK-INFRA-003) → `OLLAMA_BASE_URL`.
- **Egress** to Mistral/Gradium/registry (open input #2).
- **STUN/TURN** URLs and TLS edge for the voice VIP (open input #1/#4) → `VOICE_STUN`.
- **Postgres** db/user/password and `CREATE EXTENSION vector` (open input #7).
- **Redis** run mode / auth / TLS (open input #8).
