#!/usr/bin/env bash
# Postgres backup for the pilot (TASK-OPS-008, ADR-0008). Custom-format pg_dump of the
# KB + pgvector database on the platform-managed Postgres (.102), run from a backend VM
# (which already has network + credentials). Uses a throwaway postgres client container
# so no client needs installing on the host. Prunes old dumps and optionally copies
# off-host. See docs/operations/backup-restore.md (RPO/RTO + restore).
#
# Auth: PGPASSWORD is read from the environment (never argv, never the crontab). The
# Ansible cron sources a 0600 env file (pg-backup.env) rendered from the vault.
#
# Usage:  PGPASSWORD=... ./pg-backup.sh
# Env:    PGHOST (default 192.168.0.102), PGPORT (5432), PGUSER (voicesupport),
#         PGDATABASE (voicesupport), PG_CLIENT_IMAGE (postgres:18-alpine),
#         BACKUP_DIR (/var/backups/voice-support/postgres), BACKUP_KEEP (14),
#         BACKUP_REMOTE (optional rsync/scp target), PGPASSWORD.
set -euo pipefail

PGHOST="${PGHOST:-192.168.0.102}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-voicesupport}"
PGDATABASE="${PGDATABASE:-voicesupport}"
PG_CLIENT_IMAGE="${PG_CLIENT_IMAGE:-postgres:18-alpine}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/voice-support/postgres}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP="${PGDATABASE}-${TS}.dump"

log() { echo "[pg-backup] $*"; }
die() { echo "[pg-backup] ERROR: $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker not found"
[ -n "${PGPASSWORD:-}" ] || die "PGPASSWORD not set"
mkdir -p "$BACKUP_DIR"

# pg_dump -Fc = compressed custom format, restorable selectively with pg_restore.
# PGPASSWORD is passed as an env var to the container, not on the command line.
docker run --rm -e PGPASSWORD -v "${BACKUP_DIR}:/backup" "$PG_CLIENT_IMAGE" \
  pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Fc -f "/backup/${DUMP}"
log "wrote ${BACKUP_DIR}/${DUMP} ($(du -h "${BACKUP_DIR}/${DUMP}" | cut -f1))"

mapfile -t old < <(ls -1t "${BACKUP_DIR}"/${PGDATABASE}-*.dump 2>/dev/null | tail -n "+$((BACKUP_KEEP + 1))")
if [ "${#old[@]}" -gt 0 ]; then rm -f "${old[@]}"; log "pruned ${#old[@]} old dump(s)"; fi

if [ -n "$BACKUP_REMOTE" ]; then
  if command -v rsync >/dev/null 2>&1; then rsync -a "${BACKUP_DIR}/${DUMP}" "$BACKUP_REMOTE/"; else scp -q "${BACKUP_DIR}/${DUMP}" "$BACKUP_REMOTE/"; fi
  log "copied off-host -> ${BACKUP_REMOTE}"
else
  log "BACKUP_REMOTE unset: dump kept on-host only (set it for VM-loss protection)"
fi
