# First-deploy runbook — eir-ai4cc-tst pilot

Chronological, zero-to-running checklist to bring the two-service stack (backend
Java + voice bridge) live on the **eir-ai4cc-tst** pilot for the **first time**, on
bare Rocky EL9 VMs. A delivery engineer should reach a passing smoke test by
following the steps in order, without tribal knowledge.

- **Topology, ports, per-tier env**: [`deployment-eir-ai4cc-tst.md`](deployment-eir-ai4cc-tst.md).
- **Repeatable release/rollback** (after the first deploy): [`release-process.md`](release-process.md).
- **Rationale**: [`ADR-0038`](../architecture/adrs/ADR-0038-pilot-deployment-architecture-eir-ai4cc-tst.md),
  [`ADR-0039`](../architecture/adrs/ADR-0039-embeddings-placement-and-provider-egress-tst.md).

> This is a **first-deploy** runbook (host provisioning + Postgres bootstrap +
> initial RAG sync happen once). For subsequent version promotions, use the
> release process; it reuses the same deploy playbook and health gates.

## At a glance

| # | Step | Where | Once? |
|---|------|-------|-------|
| 0 | Confirm access + open inputs | control node → all VMs | — |
| 1 | Publish the release images | CI (git tag) → GHCR | per version |
| 2 | Populate the vault (secrets + registry token) | control node | once |
| 3 | Provision the container runtime | `prereqs.yml` | once/host |
| 4 | Bootstrap PostgreSQL + `vector` extension | data VM `.102` | once |
| 5 | Deploy Redis | `deploy.yml --limit redis` | per version |
| 6 | Deploy backend (+ auto model pull) + first RAG sync | `deploy.yml --limit backend` | per version |
| 7 | Deploy voice bridge | `deploy.yml --limit voice` | per version |
| 8 | Load balancer / TLS edge | platform / `deploy/haproxy/` | once |
| 9 | Smoke test | control node | per version |

All Ansible commands run from `deploy/ansible/`. `image_tag` is the **image** tag
(no `v` prefix — see step 1). Provide the vault password with `--ask-vault-pass`,
or drop it into the git-ignored `deploy/ansible/.vault_pass` (auto-loaded via
`ansible.cfg`).

## Step 0 — Access and open inputs

- **SSH** reaches every VM: `ssh grimaud@<hostname>.prod.lan` then `sudo su -`
  (public key already installed). The VMs live on the tenant subnet
  `192.168.0.0/24`; from outside you need the VPN/bastion route to that subnet
  (**open input #1** — ingress/SSH source range). Deployment cannot start until
  this route is up.
- Review the tracked open inputs in
  [`deployment-eir-ai4cc-tst.md`](deployment-eir-ai4cc-tst.md#open-inputs-needed)
  (owner + status + gate, TASK-INFRA-006). All self-owned items are closed; the
  residual **platform-owned** gates are **#1a** SSH/ingress CIDR, **#4** TLS cert +
  FQDN, **#11** Prod→VIP NAT mapping, **#12** STUN/TURN relay + credentials, and the
  platform side of **#10** LB apply (NIC/VRID/secret). Steps 3–7 and the backend/text
  smoke (step 9, tier A) need none of these; the **full browser voice turn** (step 9,
  tier B) needs #4 + #11 + #12.

## Step 1 — Publish the release images

Images are produced by CI, never by hand (`.github/workflows/images.yml`).

```bash
git tag v0.4.0            # git tag keeps the leading v
git push origin v0.4.0    # triggers the tests gate, then build + push
```

> **Tag gotcha (verify before deploying).** `docker/metadata-action`
> (`type=semver,pattern={{version}}`) **strips the leading `v`**: git tag
> `v0.4.0` publishes the **image** tag `0.4.0` (plus `sha-<short>`, and `latest`
> only on the mainline). So the deploy uses `image_tag=0.4.0`, **not** `v0.4.0`.

Confirm both private packages exist at that tag before deploying (read-only PAT
`vault_registry_token`, GitHub user `tgrimaud`):

```bash
echo "$PAT" | docker login ghcr.io -u tgrimaud --password-stdin
docker buildx imagetools inspect ghcr.io/tgrimaud/voice-support-backend:0.4.0
docker buildx imagetools inspect ghcr.io/tgrimaud/voice-support-voice:0.4.0
docker logout ghcr.io
```

## Step 2 — Populate the vault

Secrets live only in the encrypted `deploy/ansible/group_vars/all/vault.yml`
(git-ignored). For a fresh checkout:

```bash
cd deploy/ansible
cp group_vars/all/vault.example.yml group_vars/all/vault.yml
$EDITOR group_vars/all/vault.yml     # fill every value (below), then:
ansible-vault encrypt group_vars/all/vault.yml
```

Required values:

| Key | Purpose |
|-----|---------|
| `vault_db_password` | Postgres app-user password (used in step 4 and the backend `.env`) |
| `vault_redis_password` | Redis `requirepass`, shared with the backend |
| `vault_mistral_api_key` | Chat LLM (cloud) |
| `vault_gradium_api_key` | STT/TTS (cloud) |
| `vault_conversation_api_key` | Shared `x-api-key`: backend `CONVERSATION_API_KEY` **==** voice `VOICE_BACKEND_API_KEY` |
| `vault_registry_username` / `vault_registry_token` | GHCR read-only pull (private packages); `registry_login_required: true` |

## Step 3 — Provision the container runtime (once per host)

Installs Docker Engine + `docker compose` v2 and opens each tier's firewalld port
(TASK-OPS-003). Idempotent, safe to re-run.

```bash
cd deploy/ansible
ansible-playbook prereqs.yml --limit 'redis:backend'      # add voice when deploying it
```

On Rocky EL9 the role passes `allowerasing` so `containerd.io` can replace the
default `podman`/`runc`. The data VM `.102` (podman pod for Postgres) is **not** a
prereqs target.

## Step 4 — Bootstrap PostgreSQL (once)

PostgreSQL 18.4 runs on `vlb-ai4cc-t01` (`.102`) as a podman pod (`podpg`). Create
the database, the `vector` extension (superuser) and the app user. Reveal the
password with `ansible-vault view group_vars/all/vault.yml`.

```bash
ssh grimaud@vlb-ai4cc-t01.prod.lan
sudo su -
podpg
psql
```
```sql
CREATE DATABASE voicesupport;
\c voicesupport
CREATE EXTENSION vector;                                   -- superuser only
CREATE USER voicesupport WITH PASSWORD '<vault_db_password>';
GRANT ALL PRIVILEGES ON DATABASE voicesupport TO voicesupport;
GRANT ALL ON SCHEMA public TO voicesupport;                -- PG15+ locks public
```

The backend runs `ddl-auto: update` + `initialize-schema: true`, so it creates the
`vector_store` (768 dim) and JPA tables on first start — hence the `SCHEMA public`
grant to the app user.

## Step 5 — Deploy Redis

Redis must be up first (shared conversation memory, ADR-0008 / TASK-BE-021).

```bash
cd deploy/ansible
ansible-playbook deploy.yml -e image_tag=0.4.0 --limit redis --ask-vault-pass --check --diff   # dry-run
ansible-playbook deploy.yml -e image_tag=0.4.0 --limit redis --ask-vault-pass                   # apply
```

Verify:

```bash
ssh grimaud@vlb-ai4cc-t02.prod.lan \
  'docker exec voice-support-redis redis-cli -a "<vault_redis_password>" ping'   # -> PONG
```

## Step 6 — Deploy the backend + first RAG sync

```bash
ansible-playbook deploy.yml -e image_tag=0.4.0 --limit backend --ask-vault-pass --check --diff
ansible-playbook deploy.yml -e image_tag=0.4.0 --limit backend --ask-vault-pass
```

The role pulls the `nomic-embed-text` model into the co-located Ollama sidecar at
deploy time (ADR-0039) and health-checks each node (`/actuator/health` → 200,
rolling `serial: 1`). The image does **not** bundle the knowledge base, so trigger
the first RAG sync to populate pgvector:

```bash
curl -fsS -X POST http://192.168.0.11:8080/api/knowledge/sync    # via the backend VIP
```

Verify health on both nodes and the VIP:

```bash
curl -fsS http://192.168.0.105:8080/api/health      # t03
curl -fsS http://192.168.0.106:8080/api/health      # t04
curl -fsS http://192.168.0.11:8080/actuator/health  # VIP -> {"status":"UP"}
```

## Step 7 — Deploy the voice bridge

```bash
ansible-playbook prereqs.yml   --limit voice --ask-vault-pass          # if not done in step 3
ansible-playbook deploy.yml    -e image_tag=0.4.0 --limit voice --ask-vault-pass --check --diff
ansible-playbook deploy.yml    -e image_tag=0.4.0 --limit voice --ask-vault-pass
```

Rolling `serial: 1` with best-effort draining (the VIP peer keeps serving). Verify
each bridge answers:

```bash
curl -fsS http://192.168.0.103:8090/    # t01 -> 200
curl -fsS http://192.168.0.104:8090/    # t02 -> 200
```

## Step 8 — Load balancer and TLS edge

HAProxy + Keepalived (two VIPs) are configured in
[`deploy/haproxy/`](../../deploy/haproxy/) (TASK-INFRA-002). Apply them on the LB
hosts `vlp-t01`/`t02` with the ordered **manual apply path** in
[`deploy/haproxy/README.md`](../../deploy/haproxy/README.md) (packages →
`ip_nonlocal_bind` → configs → substitute NIC/VRID/VRRP-secret → cert → validate →
enable → failover test). The platform team confirms the NIC name, `virtual_router_id`
uniqueness and the VRRP secret (**#10**). The public FQDN + TLS cert at the voice edge
are **open input #4**; WebRTC **media** is UDP, peer-to-peer to the answering bridge
and needs a STUN/TURN relay (**#12**) — the runtime is already wired for it
(`VOICE_TURN`/`VOICE_TURN_USERNAME`/`VOICE_TURN_CREDENTIAL`), pending a relay endpoint
+ credentials. Media is never proxied by HAProxy.

## Step 9 — Smoke test

**Tier A — backend + RAG (no TLS/TURN needed).** A grounded answer proves the DB,
pgvector, embeddings sidecar, RAG and Mistral chat all work end to end:

```bash
curl -fsS -X POST http://192.168.0.11:8080/api/conversation/converse \
  -H 'content-type: application/json' \
  -H 'x-api-key: <vault_conversation_api_key>' \
  -d '{"transcript":"Pourquoi ma facture a augmenté ce mois-ci ?","conversation_id":"smoke-1","channel":"smoke","language":"fr"}'
```

Expect HTTP 200 with a non-empty `{"text": "..."}`. An `x-api-key` mismatch returns
401 (empty body) — verify the shared-secret parity from step 2. Repeat with the
same `conversation_id` to confirm shared memory (Redis) keeps context.

**Tier B — full voice turn (final acceptance).** Once the TLS edge (#4) and
STUN/TURN (#1) are in place, open the voice UI at the voice VIP over HTTPS, speak a
billing question, and confirm an audible answer plus a coherent transcript (see the
QA voice-turn checklist,
[`docs/qa/`](../qa/)). This closes the acceptance criterion.

## Rollback (known-good)

Roll back by redeploying the previous good **image** tag — same path, same health
gates (no divergent rollback code):

```bash
cd deploy/ansible
ansible-playbook rollback.yml -e image_tag=0.3.0 --ask-vault-pass         # add --limit <tier> to scope
```

Pick the previous tag from the GHCR packages. `latest` is refused so every deploy
stays reproducible and rollback-addressable.

## Troubleshooting (first-deploy)

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `manifest ... not found` on pull | Used the git tag `v0.4.0` as the image tag | Deploy with `image_tag=0.4.0` (no `v`, see step 1) |
| `docker login` denied at deploy | Missing/expired `vault_registry_token`, or `registry_login_required` false | Refresh the PAT (`read:packages`) in the vault; confirm `registry_login_required: true` |
| Backend fails on first start (pgvector) | `CREATE EXTENSION vector` not run, or app user lacks `SCHEMA public` | Re-run step 4 as superuser; grant `SCHEMA public` to `voicesupport` |
| RAG answers are ungrounded / empty | First `POST /api/knowledge/sync` not run, or KB assets missing under `KB_HOST_PATH` | Confirm `knowledge-base/` + `articles.csv` on the host, re-run the sync |
| `/actuator/health` flips DOWN | `REDIS_HEALTH_ENABLED=true` without a reachable Redis | Only enable it on the backend once Redis is deployed (step 5); default off |
| `dnf` conflict on `containerd.io` | Rocky EL9 ships `podman`/`runc` | Already handled by `allowerasing` in `prereqs.yml`; ensure `.102` is excluded |
| Embeddings model pull times out | `registry.ollama.ai:443` egress denied | Allow the egress, or pre-seed the model into the `ollama-models` volume (ADR-0039) |
| KB read-only mount denied (SELinux) | AVC on the `:ro` bind | Add `:Z` to the KB mount (documented in the compose stack) |

## Related

- Repeatable release/rollback: [`release-process.md`](release-process.md)
- Backup & restore (Redis + Postgres): [`backup-restore.md`](backup-restore.md)
- Topology / ports / env: [`deployment-eir-ai4cc-tst.md`](deployment-eir-ai4cc-tst.md)
- Ansible deploy: [`../../deploy/ansible/README.md`](../../deploy/ansible/README.md)
- Compose stacks: [`../../deploy/compose/README.md`](../../deploy/compose/README.md)
- Delivery workflow: [`development-workflow.md`](development-workflow.md)
