# Ansible deploy — eir-ai4cc-tst (TASK-OPS-002)

Deploys the released Docker images (built and pushed by CI, TASK-OPS-001) to the
tst VMs over SSH, reproducibly, with a documented rollback and best-effort voice
session draining. It drives the per-tier `docker compose` stacks from
`deploy/compose/` (TASK-INFRA-001).

> Full operational runbook: [`docs/operations/release-process.md`](../../docs/operations/release-process.md).
> Topology and env reference: [`docs/operations/deployment-eir-ai4cc-tst.md`](../../docs/operations/deployment-eir-ai4cc-tst.md).

## Layout

```
deploy/ansible/
├── ansible.cfg                 # inventory path, remote_user=grimaud, sudo become
├── inventory/hosts.ini         # the 8 VMs in per-tier groups (redis/backend/voice + data/lb ref)
├── group_vars/
│   ├── all/vars.yml            # registry, image_tag, compose_root (non-secret)
│   ├── all/vault.example.yml   # secrets TEMPLATE -> copy to vault.yml + ansible-vault encrypt
│   ├── backend.yml             # backend tier config (mirrors compose/backend/.env.example)
│   ├── voice.yml               # voice tier config + draining knobs
│   └── redis.yml               # redis tier config
├── roles/
│   ├── host_prereqs/tasks/main.yml   # install Docker Engine + compose v2 + firewalld (Rocky EL9)
│   └── compose_tier/                 # generic: dir + compose copy + .env render + pull + up + health
│       ├── tasks/{main,drain,health,kb_assets,ollama_model}.yml
│       └── templates/{backend,voice,redis}.env.j2
├── prereqs.yml                 # one-time host provisioning (Docker) on redis/backend/voice
├── deploy.yml                  # redis -> backend (rolling) -> voice (rolling, drained)
└── rollback.yml                # redeploy a pinned previous tag (imports deploy.yml)
```

## Prerequisites

- Control node: `ansible-core` >= 2.15 (`pip install ansible-core`).
- Targets: SSH key access for `grimaud` with `sudo`. The Docker Engine + `docker
  compose` v2 plugin are installed by `prereqs.yml` (run once per fresh host, below).
- Secrets: `cp group_vars/all/vault.example.yml group_vars/all/vault.yml`, fill it,
  then `ansible-vault encrypt group_vars/all/vault.yml` (the real file is git-ignored).
- A published, immutable **image** tag — never `latest`. Note the image tag has
  **no `v`** (git tag `vX.Y.Z` → image tag `X.Y.Z`, e.g. `0.4.0`), plus
  `sha-xxxxxxx`. See `docs/operations/release-process.md`.

## Usage

```bash
cd deploy/ansible

# One-time: provision the container runtime on bare VMs (idempotent, safe to re-run):
ansible-playbook prereqs.yml                       # all deploy tiers
ansible-playbook prereqs.yml --limit redis         # a single tier

# Dry-run first (no changes). image_tag is the IMAGE tag (no leading v):
ansible-playbook deploy.yml -e image_tag=1.2.0 --ask-vault-pass --check --diff

# Deploy a version to tst:
ansible-playbook deploy.yml -e image_tag=1.2.0 --ask-vault-pass

# Deploy a single tier:
ansible-playbook deploy.yml -e image_tag=1.2.0 --ask-vault-pass --limit voice

# Roll back to the previous good version:
ansible-playbook rollback.yml -e image_tag=1.1.0 --ask-vault-pass
```

`image_tag` is mandatory and `latest` is refused, so every deploy is reproducible
and rollback-addressable. The `.env` is rendered on each host with mode `0600` and
`no_log`; secrets never appear in Ansible output.

## Voice session draining (best-effort — known limitation)

The bridge exposes no active-session count or `/drain` endpoint yet, so a hard
"wait until 0 active calls" is not possible from the outside. Draining is:

1. **serial:1 rolling** — only one bridge recreates at a time; the VIP peer keeps serving;
2. **LB node-down/up hook** (`voice_lb_drain_cmd` / `voice_lb_enable_cmd`, TASK-INFRA-007) —
   sets this bridge to `state drain`/`ready` on every LB node via the HAProxy admin
   socket (`socat … /run/haproxy/admin.sock`), delegated to `voice_lb_socket_hosts`,
   so NEW calls stop hitting the node while it recreates. **Opt-in:** `voice_lb_socket_hosts`
   defaults to **empty** (the `[lb]` group is platform-managed, SSH not confirmed yet —
   gated with TASK-INFRA-006), so the hook is off by default and the deploy runs grace-only.
   Enable it once LB access exists with
   `-e '{"voice_lb_socket_hosts":["vlp-ai4cc-t01.prod.lan","vlp-ai4cc-t02.prod.lan"]}'`.
   Even enabled, the delegated tasks are non-fatal (`ignore_unreachable` + `failed_when: false`):
   a failing LB hook degrades to grace-only with a warning, it never aborts the deploy;
3. **bounded grace** (`voice_drain_grace_seconds`, default 60s) — lets an in-flight
   call wind down before recreate.

Remaining path for an *exact* drain: add a bridge `/drain` + active-session endpoint
(follow-up) so the fixed grace becomes a poll-until-zero wait. The LB node-down hook
above already stops new calls; this is a tracked limitation, not a silent gap.
