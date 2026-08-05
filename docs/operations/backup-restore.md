# Backup & restore — eir-ai4cc-tst pilot (Redis + Postgres)

Data durability for the pilot's two stateful stores (TASK-OPS-008, ADR-0008/ADR-0038).
The topology has **one** Postgres (`.102`, KB + pgvector) and **one** Redis (`.107`,
conversation memory) with no replica — losing either VM without a backup is data loss.
This runbook makes both **backed up off-host and restorable**. High availability
(replica / Sentinel / PITR) is intentionally *out of scope* here — this is durability,
not zero-downtime.

> Scripts: [`../../deploy/backup/`](../../deploy/backup/). Scheduling is wired by the
> Ansible `compose_tier` role (`tasks/backup.yml`); tune via `group_vars/redis.yml`
> and `group_vars/backend.yml`.

## At a glance

| Store | What is backed up | Continuous layer | Scheduled artifact | Default RPO | Default RTO |
|-------|-------------------|------------------|--------------------|-------------|-------------|
| Redis `.107` | `dump.rdb` + AOF (`/data`) | AOF `appendfsync everysec` (~1s) | hourly `BGSAVE` tar (`redis-backup.sh`) | ≤ 1 h (snapshot) / ~1 s (AOF, same host) | ~5 min |
| Postgres `.102` | `pg_dump -Fc` of `voicesupport` (KB, pgvector, conversation events) | — | daily custom-format dump (`pg-backup.sh`) | ≤ 24 h | ~10–20 min (dump) or re-sync KB |

- **RPO** (max data loss) is bounded by the schedule; shrink it by lowering the cron
  interval or, for a real VM-loss event, by setting an **off-host** target (below).
- **RTO** (time to restore) assumes the dump/snapshot is already off-host and a target
  DB/Redis is reachable. Recreating a VM from scratch adds provisioning time.

## Where backups go

Both jobs write to a local directory and — only if configured — copy off-host:

| Var (`group_vars`) | Default | Purpose |
|--------------------|---------|---------|
| `redis_backup_dir` / `pg_backup_dir` | `/var/backups/voice-support/{redis,postgres}` | on-host snapshot dir |
| `redis_backup_remote` / `pg_backup_remote` | `""` (unset) | rsync/scp target for off-host copy |
| `redis_backup_keep` / `pg_backup_keep` | 168 / 14 | retention (newest N kept) |

> **Set the `*_remote` targets.** An on-host-only backup does **not** survive losing the
> VM — which is the SPOF this ticket addresses. Point them at a host outside the DB/Redis
> VM (e.g. the reference `vlb-ai4cc-t01` or a platform backup share) with key-based SSH.

## Redis

### Backup (automatic)

The Ansible role installs `redis-backup.sh` + an hourly cron on the redis host. Each run
triggers `BGSAVE`, tars `/data` (RDB + AOF) to `redis-<ts>.tar.gz`, prunes to
`redis_backup_keep`, and copies off-host when `redis_backup_remote` is set. The Redis
password is read from `REDISCLI_AUTH` in a `0600` env file — never the crontab.

Run on demand:

```bash
cd /opt/voice-support/redis/backup
. ./redis-backup.env && BACKUP_DIR=/var/backups/voice-support/redis ./redis-backup.sh
```

### Restore (destructive)

```bash
cd /opt/voice-support/redis/backup
./redis-restore.sh /var/backups/voice-support/redis/redis-<ts>.tar.gz
# verify:
docker exec voice-support-redis redis-cli -e DBSIZE
```

It stops Redis, replaces `/data` from the archive, and restarts. Conversation sessions
older than `CONVERSATION_MEMORY_TTL_SECONDS` (default 1 h) expire naturally after restore.

## Postgres

### Backup (automatic)

The role installs `pg-backup.sh` + a daily cron on **one** backend node (it dumps the
shared `.102`, so one node is enough). It runs `pg_dump -Fc` inside a throwaway
`postgres:16-alpine` container (no client install), prunes to `pg_backup_keep`, and copies
off-host when `pg_backup_remote` is set. `PGPASSWORD` comes from a `0600` env file.

Run on demand:

```bash
cd /opt/voice-support/backend/backup
set -a; . ./pg-backup.env; set +a; BACKUP_DIR=/var/backups/voice-support/postgres ./pg-backup.sh
```

### Restore (two options)

1. **Restore the dump** — recovers exact vectors + conversation-event history:

```bash
cd /opt/voice-support/backend/backup
set -a; . ./pg-backup.env; set +a
./pg-restore.sh /var/backups/voice-support/postgres/voicesupport-<ts>.dump
```

The script creates the DB if missing, ensures `CREATE EXTENSION vector`, then
`pg_restore --clean --if-exists --no-owner`.

2. **Rebuild the KB from source** — if no fresh dump exists, the KB is reproducible: after
   the schema exists (`CREATE EXTENSION vector`), start the backend and
   `POST /api/knowledge/sync` re-ingests `knowledge-base/` (embeddings recomputed). Note:
   this recovers the KB, **not** past conversation events.

Verify:

```sql
SELECT count(*) FROM vector_store;   -- KB chunks present
```

## Restore drill (verification)

Acceptance requires a restore verified into a clean target at least once. Suggested drill,
run in the tst window once LB/host SSH access is available (gated with the other live
checks by **TASK-INFRA-006**):

1. Provision a scratch Postgres (or an empty DB name) + a scratch Redis container.
2. Restore the latest dump/snapshot into them with the scripts above.
3. Assert `SELECT count(*) FROM vector_store` matches the source and a sample
   `POST /api/conversation/ask` still grounds; assert Redis `DBSIZE` > 0.
4. Record the measured RTO next to the defaults in this doc.

Until that window, the tooling + schedule are validated offline
(`deploy/ansible/qa-validate-ansible.sh`, `bash -n` on the scripts).

## Related

- Backup scripts: [`../../deploy/backup/`](../../deploy/backup/)
- Repeatable release/rollback: [`release-process.md`](release-process.md)
- First deploy (DB bootstrap, KB sync): [`first-deploy-runbook.md`](first-deploy-runbook.md)
- Topology / ports: [`deployment-eir-ai4cc-tst.md`](deployment-eir-ai4cc-tst.md)
