#!/usr/bin/env bash
# Redis backup for the pilot (TASK-OPS-008, ADR-0008). Point-in-time snapshot of the
# conversation-memory Redis: triggers BGSAVE, copies the RDB + AOF out of the container
# to a timestamped tar, prunes old snapshots, and optionally copies off-host.
#
# Continuous durability is AOF (`--appendonly yes`, ~1s RPO on `everysec`); this job is
# the off-host, restorable artifact (see docs/operations/backup-restore.md).
#
# Auth: the Redis password is read from REDISCLI_AUTH in the environment (never argv,
# never the crontab). The Ansible cron sources a 0600 env file (redis-backup.env).
#
# Usage:  REDISCLI_AUTH=... ./redis-backup.sh
# Env:    REDIS_CONTAINER (default voice-support-redis), BACKUP_DIR (default
#         /var/backups/voice-support/redis), BACKUP_KEEP (default 168 snapshots),
#         BACKUP_REMOTE (optional rsync/scp target, e.g. user@host:/path), REDISCLI_AUTH.
set -euo pipefail

REDIS_CONTAINER="${REDIS_CONTAINER:-voice-support-redis}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/voice-support/redis}"
BACKUP_KEEP="${BACKUP_KEEP:-168}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="${BACKUP_DIR}/redis-${TS}.tar.gz"

log() { echo "[redis-backup] $*"; }
die() { echo "[redis-backup] ERROR: $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker not found"
docker inspect "$REDIS_CONTAINER" >/dev/null 2>&1 || die "container ${REDIS_CONTAINER} not running"
[ -n "${REDISCLI_AUTH:-}" ] || die "REDISCLI_AUTH not set (Redis requirepass is enabled)"

mkdir -p "$BACKUP_DIR"

# Trigger a background save and wait until it completes (LASTSAVE advances). redis-cli
# reads the password from REDISCLI_AUTH so it never appears in argv/process list.
before="$(docker exec -e REDISCLI_AUTH="$REDISCLI_AUTH" "$REDIS_CONTAINER" redis-cli LASTSAVE | tr -d '\r')"
docker exec -e REDISCLI_AUTH="$REDISCLI_AUTH" "$REDIS_CONTAINER" redis-cli BGSAVE >/dev/null
for _ in $(seq 1 60); do
  now="$(docker exec -e REDISCLI_AUTH="$REDISCLI_AUTH" "$REDIS_CONTAINER" redis-cli LASTSAVE | tr -d '\r')"
  [ "$now" != "$before" ] && break
  sleep 1
done
[ "${now:-$before}" != "$before" ] || die "BGSAVE did not complete within 60s"

# Copy the whole /data (dump.rdb + appendonlydir) out of the container and tar it.
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
docker cp "${REDIS_CONTAINER}:/data/." "$tmp/"
tar -czf "$ARCHIVE" -C "$tmp" .
log "wrote ${ARCHIVE} ($(du -h "$ARCHIVE" | cut -f1))"

# Retention: keep the newest BACKUP_KEEP archives.
mapfile -t old < <(ls -1t "${BACKUP_DIR}"/redis-*.tar.gz 2>/dev/null | tail -n "+$((BACKUP_KEEP + 1))")
if [ "${#old[@]}" -gt 0 ]; then rm -f "${old[@]}"; log "pruned ${#old[@]} old snapshot(s)"; fi

# Optional off-host copy (rsync if available, else scp). Off-host is what protects
# against losing the Redis VM entirely (the ticket's SPOF concern).
if [ -n "$BACKUP_REMOTE" ]; then
  if command -v rsync >/dev/null 2>&1; then rsync -a "$ARCHIVE" "$BACKUP_REMOTE/"; else scp -q "$ARCHIVE" "$BACKUP_REMOTE/"; fi
  log "copied off-host -> ${BACKUP_REMOTE}"
else
  log "BACKUP_REMOTE unset: snapshot kept on-host only (set it for VM-loss protection)"
fi
