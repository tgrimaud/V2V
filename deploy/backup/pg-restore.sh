#!/usr/bin/env bash
# Postgres restore for the pilot (TASK-OPS-008). Restores a pg-backup.sh custom-format
# dump into a (possibly clean) Postgres, recreating the pgvector extension. Uses a
# throwaway postgres client container. See docs/operations/backup-restore.md (RPO/RTO).
#
# The KB can also be rebuilt from source instead of restored: after the schema exists,
# `POST /api/knowledge/sync` re-ingests knowledge-base/ (embeddings recomputed). Restore
# the dump to recover exact vectors + conversation-event history; re-sync if the dump is
# stale or missing.
#
# Usage:  PGPASSWORD=... ./pg-restore.sh /var/backups/voice-support/postgres/<db>-<ts>.dump
# Env:    PGHOST (192.168.0.102), PGPORT (5432), PGUSER (voicesupport),
#         PGDATABASE (voicesupport), PG_CLIENT_IMAGE (postgres:16-alpine), PGPASSWORD.
set -euo pipefail

DUMP="${1:-}"
PGHOST="${PGHOST:-192.168.0.102}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-voicesupport}"
PGDATABASE="${PGDATABASE:-voicesupport}"
PG_CLIENT_IMAGE="${PG_CLIENT_IMAGE:-postgres:16-alpine}"

log() { echo "[pg-restore] $*"; }
die() { echo "[pg-restore] ERROR: $*" >&2; exit 1; }

[ -n "$DUMP" ] || die "usage: $0 <dump-file>"
[ -f "$DUMP" ] || die "dump not found: $DUMP"
command -v docker >/dev/null 2>&1 || die "docker not found"
[ -n "${PGPASSWORD:-}" ] || die "PGPASSWORD not set"

dump_dir="$(cd "$(dirname "$DUMP")" && pwd)"
dump_name="$(basename "$DUMP")"
psql_run() { docker run --rm -e PGPASSWORD "$PG_CLIENT_IMAGE" psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" "$@"; }

# Ensure the database exists (no-op if already there), then the pgvector extension.
if ! psql_run -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${PGDATABASE}'" | grep -q 1; then
  log "creating database ${PGDATABASE}"
  psql_run -d postgres -c "CREATE DATABASE \"${PGDATABASE}\""
fi
log "ensuring pgvector extension"
psql_run -d "$PGDATABASE" -c "CREATE EXTENSION IF NOT EXISTS vector"

log "restoring ${dump_name} (pg_restore --clean --if-exists)"
docker run --rm -e PGPASSWORD -v "${dump_dir}:/backup:ro" "$PG_CLIENT_IMAGE" \
  pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
  --clean --if-exists --no-owner "/backup/${dump_name}"

log "restore complete — verify: SELECT count(*) FROM vector_store; then optionally POST /api/knowledge/sync"
