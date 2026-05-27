#!/bin/bash
# Backup PostgreSQL database for Kojo bot
# Usage: ./scripts/backup_postgres.sh [output_dir]
set -euo pipefail

BACKUP_DIR="${1:-/var/backups/kojo}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/kojo_db_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=7
LOCK_FILE="/tmp/kojo_backup.lock"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
DOCKER_COMPOSE_DIR="${SCRIPT_DIR}/docker"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
error() { log "ERROR: $*" >&2; }

cleanup() { rm -f "$LOCK_FILE"; }
trap cleanup EXIT

if [ -f "$LOCK_FILE" ]; then
    error "Another backup is already running (lock: $LOCK_FILE)"
    exit 1
fi
touch "$LOCK_FILE"

mkdir -p "$BACKUP_DIR"

# Try to read DB URL from .env
DB_URL=""
if [ -f "$ENV_FILE" ]; then
    DB_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | sed 's/^DATABASE_URL=//' | tr -d '"'"'"' || true)
fi

if [ -z "$DB_URL" ]; then
    # Default for docker-compose environment
    DB_HOST="${PGHOST:-RAG_kojo-db}"
    DB_PORT="${PGPORT:-5432}"
    DB_NAME="${PGDATABASE:-kojo_db}"
    DB_USER="${PGUSER:-kojo_user}"
    DB_PASSWORD="${PGPASSWORD:-kojo_password}"
else
    DB_HOST=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@\([^:]*\):\([0-9]*\)/\(.*\)|\2|p')
    DB_PORT=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@\([^:]*\):\([0-9]*\)/\(.*\)|\3|p')
    DB_NAME=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@\([^:]*\):\([0-9]*\)/\(.*\)|\4|p')
    DB_USER=$(echo "$DB_URL" | sed -n 's|.*://\([^:]*\):\([^@]*\)@.*|\1|p')
    DB_PASSWORD=$(echo "$DB_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
fi

export PGPASSWORD="${DB_PASSWORD}"

log "Starting backup: ${DB_NAME}@${DB_HOST}:${DB_PORT} -> ${BACKUP_FILE}"

pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --no-owner \
    --no-acl \
    --format=custom \
    --compress=9 \
    --file="${BACKUP_DIR}/kojo_db_${TIMESTAMP}.dump" \
    2>&1 | while read -r line; do log "[pg_dump] $line"; done

log "Backup completed: ${BACKUP_DIR}/kojo_db_${TIMESTAMP}.dump"

# Cleanup old backups (older than RETENTION_DAYS)
log "Cleaning backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -name 'kojo_db_*.dump' -mtime "+${RETENTION_DAYS}" -delete
find "$BACKUP_DIR" -name 'kojo_db_*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete

log "Backup finished successfully"
log "Disk usage: $(du -sh "$BACKUP_DIR" | cut -f1)"
log "Backup files: $(find "$BACKUP_DIR" -name 'kojo_db_*' | wc -l)"
