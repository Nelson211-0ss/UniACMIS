#!/usr/bin/env bash
# Nightly database backup (NFR-DATA-01).
#
# Runs pg_dump inside the `db` container — the postgres:16-alpine image ships
# the client tools; the `backend` image deliberately does not (it only needs
# psycopg's bundled libpq, not the standalone CLI — see backend/Dockerfile).
# Writes a gzipped, timestamped dump to $BACKUP_DIR, prunes anything older
# than $BACKUP_RETENTION_DAYS, and — only if $OFFSITE_BACKUP_DIR is set to a
# mounted path (network share, rclone mount, whatever the campus has) —
# copies the fresh dump there too. No off-site target is confirmed yet (see
# docs/TRACEABILITY.md open items), so replication is opportunistic and its
# absence is not a failure: only the local dump failing is.
#
# Usage: scripts/backup_database.sh
# Cron:  0 2 * * * cd /path/to/UniACMIS && scripts/backup_database.sh >> /var/log/uniacmis-backup.log 2>&1

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

BACKUP_DIR="${BACKUP_DIR:-$(pwd)/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
POSTGRES_DB="${POSTGRES_DB:-uniacmis}"
POSTGRES_USER="${POSTGRES_USER:-uniacmis}"
DC="${DC:-docker compose}"

timestamp() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "[$(timestamp)] $*"; }

mkdir -p "$BACKUP_DIR"
dump_file="$BACKUP_DIR/uniacmis-$(date -u '+%Y%m%d-%H%M%S').sql.gz"

log "Starting backup of '$POSTGRES_DB' -> $dump_file"

if ! $DC exec -T db pg_dump -U "$POSTGRES_USER" --format=plain "$POSTGRES_DB" \
    | gzip > "$dump_file"; then
    log "ERROR: pg_dump failed. Removing partial file."
    rm -f "$dump_file"
    exit 1
fi

if [ ! -s "$dump_file" ]; then
    log "ERROR: backup file is empty."
    rm -f "$dump_file"
    exit 1
fi

log "Backup written: $dump_file ($(du -h "$dump_file" | cut -f1))"

if [ -n "${OFFSITE_BACKUP_DIR:-}" ]; then
    if mkdir -p "$OFFSITE_BACKUP_DIR" 2>/dev/null && cp "$dump_file" "$OFFSITE_BACKUP_DIR/"; then
        log "Replicated off-site to $OFFSITE_BACKUP_DIR"
    else
        log "WARNING: off-site replication to $OFFSITE_BACKUP_DIR failed — local backup still stands."
    fi
else
    log "OFFSITE_BACKUP_DIR not set — skipping off-site replication."
fi

log "Pruning local backups older than $RETENTION_DAYS day(s)."
find "$BACKUP_DIR" -maxdepth 1 -name 'uniacmis-*.sql.gz' -mtime "+$RETENTION_DAYS" -print -delete

log "Backup complete."
