#!/usr/bin/env bash
# Restore a database backup (NFR-DATA-01) — "an untested backup is not a
# backup" (docs/ARCHITECTURE.md §11). Run this after every change to
# backup_database.sh, and periodically against a scratch database, so the
# procedure is proven before it is ever needed for real.
#
# This DROPS AND RECREATES the target database. It refuses to run without
# an explicit --yes, on top of Bash's own destructive-command caution.
#
# Usage: scripts/restore_database.sh <path-to-dump.sql.gz> --yes [--db NAME]

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

DC="${DC:-docker compose}"
POSTGRES_USER="${POSTGRES_USER:-uniacmis}"
POSTGRES_DB="${POSTGRES_DB:-uniacmis}"
CONFIRMED=false
DUMP_FILE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --yes) CONFIRMED=true; shift ;;
        --db) POSTGRES_DB="$2"; shift 2 ;;
        *) DUMP_FILE="$1"; shift ;;
    esac
done

if [ -z "$DUMP_FILE" ] || [ ! -f "$DUMP_FILE" ]; then
    echo "Usage: $0 <path-to-dump.sql.gz> --yes [--db NAME]" >&2
    exit 1
fi

if [ "$CONFIRMED" != true ]; then
    echo "This drops and recreates database '$POSTGRES_DB' before loading $DUMP_FILE." >&2
    echo "Re-run with --yes to proceed." >&2
    exit 1
fi

timestamp() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "[$(timestamp)] $*"; }

log "Terminating other connections to '$POSTGRES_DB'."
$DC exec -T db psql -U "$POSTGRES_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$POSTGRES_DB' AND pid <> pg_backend_pid();" \
    >/dev/null

log "Dropping and recreating '$POSTGRES_DB'."
$DC exec -T db psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";"
$DC exec -T db psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"

log "Loading $DUMP_FILE"
gunzip -c "$DUMP_FILE" | $DC exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null

log "Restore complete. Run 'make migrate' if the dump predates the current migrations."
