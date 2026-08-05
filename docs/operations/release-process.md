# Release process — eir-ai4cc-tst pilot

How to promote, deploy, verify and roll back a version of the two-service stack
(backend Java + voice bridge) on the tst environment. This is the operational
companion to the topology reference
[`deployment-eir-ai4cc-tst.md`](deployment-eir-ai4cc-tst.md).

- **Build/publish**: GitHub Actions (`TASK-OPS-001`) — `.github/workflows/`.
- **Deploy/rollback**: Ansible (`TASK-OPS-002`) — [`deploy/ansible/`](../../deploy/ansible/).
- **Per-tier stacks**: docker-compose (`TASK-INFRA-001`) — [`deploy/compose/`](../../deploy/compose/).

## Roles and boundaries

| Concern | Owner | Where |
|---------|-------|-------|
| Run tests, build + push images | CI (GitHub Actions) | `.github/workflows/{tests,ci,images}.yml` |
| Immutable image tags (`vX.Y.Z`, `sha-xxxxxxx`) | CI | GHCR (`ghcr.io/<owner>/voice-support-{backend,voice}`) |
| Deploy a tag to the VMs | Ansible over SSH | `deploy/ansible/deploy.yml` |
| Roll back to a previous tag | Ansible over SSH | `deploy/ansible/rollback.yml` |
| Secrets | Ansible Vault (rendered to `.env` per host) | `group_vars/all/vault.yml` |

## Prerequisites (once)

1. **CI is green** on the mainline and images are published (see "Promote a version").
2. **Control node** has `ansible-core >= 2.15` (`pip install ansible-core`).
3. **SSH + sudo** for `grimaud` on every target VM (`ssh grimaud@<host>.mt.lan`, then sudo).
4. **Targets** have Docker Engine + the `docker compose` v2 plugin — provision bare
   Rocky EL9 VMs once with `ansible-playbook prereqs.yml` (TASK-OPS-003; idempotent,
   installs Docker + compose v2 + opens each tier's firewalld port).
5. **Vault** is populated:
   ```bash
   cd deploy/ansible
   cp group_vars/all/vault.example.yml group_vars/all/vault.yml
   $EDITOR group_vars/all/vault.yml          # DB, Mistral, Gradium, Redis, shared API key
   ansible-vault encrypt group_vars/all/vault.yml
   ```
   The shared API key must satisfy: backend `CONVERSATION_API_KEY` == voice
   `VOICE_BACKEND_API_KEY` (both rendered from `vault_conversation_api_key`).
6. **Postgres** database exists with `CREATE EXTENSION vector;` (see the deployment
   reference); **Redis** tier is reachable (or provided by the platform).
7. **Knowledge base assets** are present on each backend host under
   `KB_HOST_PATH` (a `knowledge-base/` folder + `articles.csv`), mounted read-only.

## Promote a version

Versions are produced by CI, never by hand.

1. Merge the change to the mainline; the CI test gate must pass.
2. Tag the release and push the tag:
   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```
3. GitHub Actions builds and pushes both images with immutable tags
   (`v1.2.0` and `sha-<commit>`). Confirm both packages exist in GHCR before deploying.

`latest` is published on the mainline for convenience but MUST NOT be used to
deploy — the playbooks refuse it so every deploy is reproducible and
rollback-addressable.

## Deploy a version to tst

```bash
cd deploy/ansible

# 1) Dry-run (no changes) to review what would happen:
ansible-playbook deploy.yml -e image_tag=v1.2.0 --ask-vault-pass --check --diff

# 2) Deploy:
ansible-playbook deploy.yml -e image_tag=v1.2.0 --ask-vault-pass
```

Deploy order (enforced by the playbook):

1. **Redis** — shared conversation memory must be up first.
2. **Backend** — rolling (`serial: 1`); each node is health-checked
   (`/actuator/health` → 200) before the next. Depends on Postgres, Redis, embeddings, Mistral.
3. **Voice** — rolling (`serial: 1`), drained before recreate; health-checked
   (`GET /` → 200). Depends on the backend VIP.

Each tier: the role copies the compose file, renders `.env` (mode `0600`,
`no_log`), `docker compose pull` at the target tag, `docker compose up -d`, then
verifies health. Re-running the same tag is idempotent.

### First deploy — populate the RAG index

Embeddings run on a co-located Ollama sidecar per backend VM (ADR-0039); the
`nomic-embed-text` model is pulled automatically during the backend deploy, so no
manual model step is needed. The image does not bundle the knowledge base, so
after the first backend deploy trigger the sync to populate pgvector:

```bash
curl -fsS -X POST http://192.168.0.11:8080/api/knowledge/sync
```

(or wait for the scheduler). Subsequent deploys keep the existing index.

## Verify

- **Backend**: `curl -fsS http://192.168.0.11:8080/actuator/health` → `{"status":"UP"}`
  on both t03/t04 (and via the VIP `.11`).
- **Voice**: `curl -fsS http://<voice-host>:8090/` → 200 on both t01/t02.
- **Redis**: `docker exec voice-support-redis redis-cli -a <pwd> ping` → `PONG`.
- **Smoke** (end to end): run one full voice turn from a client and confirm an
  audio answer plus a coherent transcript (see the QA voice-turn checklist).

## Roll back

Roll back by redeploying the previous good immutable tag — same path, same health
gates, no divergent rollback code:

```bash
cd deploy/ansible
ansible-playbook rollback.yml -e image_tag=v1.1.0 --ask-vault-pass
```

Pick the previous tag from the GHCR packages. To roll back a single tier, add
`--limit backend` (or `voice`). Verify health as above.

## Voice session draining (best-effort — known limitation)

Restarting a voice bridge must avoid hard-cutting active calls. The bridge has no
active-session count or `/drain` endpoint yet, so an exact "wait until 0 active
calls" cannot be done from the outside. Draining is therefore best-effort:

1. **Rolling `serial: 1`** — only one bridge recreates at a time; the VIP peer
   keeps serving new and existing calls.
2. **LB node-down/up hook** — `voice_lb_drain_cmd` marks the node down at the load
   balancer so NEW calls stop hitting it during recreate, `voice_lb_enable_cmd`
   restores it once healthy. Empty until HAProxy is configured (`TASK-INFRA-002`);
   the playbook prints a warning when unset.
3. **Bounded grace** — `voice_drain_grace_seconds` (default 60s) lets an in-flight
   call wind down before the container is recreated.

**To make draining exact**, complete one of:

- **HAProxy node-down** (`TASK-INFRA-002`): set `voice_lb_drain_cmd` /
  `voice_lb_enable_cmd` to the socket/admin command that disables the backend
  server, so new calls are provably stopped before recreate; or
- **Bridge `/drain` endpoint** (follow-up): expose active-session count and a
  drain mode on the voice bridge, and replace the fixed grace with a poll-until-zero
  (bounded) wait.

Until then, prefer deploying voice during a low-traffic window.

## Secrets handling

- Secrets live only in `group_vars/all/vault.yml` (Ansible Vault, git-ignored).
- Rendered `.env` files are written on the target with mode `0600`; the templating
  task uses `no_log`, so secrets never appear in Ansible output.
- Registry login (private registry only) uses `--password-stdin` under `no_log`.
- Rotate a secret by editing the vault (`ansible-vault edit ...`) and redeploying;
  never edit a rendered `.env` on a host by hand (the next deploy overwrites it).

## Related

- Topology, ports, per-tier env: [`deployment-eir-ai4cc-tst.md`](deployment-eir-ai4cc-tst.md)
- CI workflows: `.github/workflows/` — QA report `docs/qa/task-ops-001-github-actions-ci-qa-report.md`
- Compose stacks: [`deploy/compose/README.md`](../../deploy/compose/README.md)
- ADR-0038 (remote deployment topology), ADR-0008 (Redis shared memory)
