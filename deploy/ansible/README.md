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
├── roles/compose_tier/         # generic: dir + compose copy + .env render + pull + up + health
│   ├── tasks/{main,drain,health}.yml
│   └── templates/{backend,voice,redis}.env.j2
├── deploy.yml                  # redis -> backend (rolling) -> voice (rolling, drained)
└── rollback.yml                # redeploy a pinned previous tag (imports deploy.yml)
```

## Prerequisites

- Control node: `ansible-core` >= 2.15 (`pip install ansible-core`).
- Targets: Docker Engine + `docker compose` v2 plugin, SSH key access for `grimaud`
  with `sudo`.
- Secrets: `cp group_vars/all/vault.example.yml group_vars/all/vault.yml`, fill it,
  then `ansible-vault encrypt group_vars/all/vault.yml` (the real file is git-ignored).
- A published, immutable image tag (`vX.Y.Z` or `sha-xxxxxxx`) — never `latest`.

## Usage

```bash
cd deploy/ansible

# Dry-run first (no changes):
ansible-playbook deploy.yml -e image_tag=v1.2.0 --ask-vault-pass --check --diff

# Deploy a version to tst:
ansible-playbook deploy.yml -e image_tag=v1.2.0 --ask-vault-pass

# Deploy a single tier:
ansible-playbook deploy.yml -e image_tag=v1.2.0 --ask-vault-pass --limit voice

# Roll back to the previous good version:
ansible-playbook rollback.yml -e image_tag=v1.1.0 --ask-vault-pass
```

`image_tag` is mandatory and `latest` is refused, so every deploy is reproducible
and rollback-addressable. The `.env` is rendered on each host with mode `0600` and
`no_log`; secrets never appear in Ansible output.

## Voice session draining (best-effort — known limitation)

The bridge exposes no active-session count or `/drain` endpoint yet, so a hard
"wait until 0 active calls" is not possible from the outside. Draining is:

1. **serial:1 rolling** — only one bridge recreates at a time; the VIP peer keeps serving;
2. **LB node-down/up hook** (`voice_lb_drain_cmd` / `voice_lb_enable_cmd`) — stops
   NEW calls hitting the node while it recreates. Empty until HAProxy is configured
   (TASK-INFRA-002); a warning is printed when unset;
3. **bounded grace** (`voice_drain_grace_seconds`, default 60s) — lets an in-flight
   call wind down before recreate.

Completion paths for an exact drain: wire the HAProxy node-down hook (INFRA-002),
or add a bridge `/drain` + active-session endpoint (follow-up). Both are documented
in the runbook so this is a tracked limitation, not a silent gap.
