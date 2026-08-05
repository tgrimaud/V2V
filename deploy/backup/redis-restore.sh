#!/usr/bin/env bash
# Redis restore for the pilot (TASK-OPS-008). Restores a redis-backup.sh archive into
# the Redis data volume. Destructive: overwrites the current /data. See
# docs/operations/backup-restore.md for the full runbook (RPO/RTO).
#
# Usage:  ./redis-restore.sh /var/backups/voice-support/redis/redis-<ts>.tar.gz
# Env:    REDIS_CONTAINER (default voice-support-redis),
#         COMPOSE_DIR (compose stack dir; default /opt/voice-support/redis).
set -euo pipefail

ARCHIVE="${1:-}"
REDIS_CONTAINER="${REDIS_CONTAINER:-voice-support-redis}"
COMPOSE_DIR="${COMPOSE_DIR:-/opt/voice-support/redis}"

log() { echo "[redis-restore] $*"; }
die() { echo "[redis-restore] ERROR: $*" >&2; exit 1; }

[ -n "$ARCHIVE" ] || die "usage: $0 <archive.tar.gz>"
[ -f "$ARCHIVE" ] || die "archive not found: $ARCHIVE"
command -v docker >/dev/null 2>&1 || die "docker not found"

if docker compose version >/dev/null 2>&1; then COMPOSE="docker compose"; else COMPOSE="docker-compose"; fi

log "stopping Redis so /data is quiescent"
( cd "$COMPOSE_DIR" && $COMPOSE stop redis )

# Recreate a throwaway container is unnecessary; restore into the stopped container's
# volume by starting a helper that shares the same named volume mount path (/data).
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
tar -xzf "$ARCHIVE" -C "$tmp"

log "clearing and repopulating /data from $(basename "$ARCHIVE")"
docker run --rm --volumes-from "$REDIS_CONTAINER" -v "$tmp:/restore:ro" alpine \
  sh -c 'rm -rf /data/* /data/..?* 2>/dev/null; cp -a /restore/. /data/'

log "starting Redis"
( cd "$COMPOSE_DIR" && $COMPOSE up -d redis )
log "restore complete — verify: docker exec ${REDIS_CONTAINER} redis-cli -e DBSIZE"
