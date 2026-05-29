#!/bin/bash
# Scheduled PostgreSQL backup script for Kojo bot service.
# Usage: KOJO_DATABASE_URL="postgresql://..." ./scripts/backup_db.sh
set -euo pipefail

# ---- config ----
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/kojo_backup_${TIMESTAMP}.dump"

# ---- resolve database URL ----
DB_URL="${KOJO_DATABASE_URL:-${DATABASE_URL:-}}"

if [ -z "$DB_URL" ]; then
    echo "ERROR: neither KOJO_DATABASE_URL nor DATABASE_URL is set" >&2
    echo "Usage: KOJO_DATABASE_URL='postgresql://user:pass@host:5432/db' $0" >&2
    exit 1
fi

# ---- preflight ----
if ! command -v pg_dump &>/dev/null; then
    echo "ERROR: pg_dump not found. Install postgresql-client." >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"

# ---- backup ----
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup -> ${BACKUP_DIR}/kojo_backup_${TIMESTAMP}.dump"

pg_dump "$DB_URL" -Fc -f "$BACKUP_FILE"

# ---- verify ----
if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: backup file was not created: $BACKUP_FILE" >&2
    exit 1
fi

FILE_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null)
if [ "$FILE_SIZE" -eq 0 ]; then
    echo "ERROR: backup file is empty: $BACKUP_FILE" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup completed: ${BACKUP_FILE} ($(numfmt --to=iec-i --suffix=B "$FILE_SIZE" 2>/dev/null || echo "${FILE_SIZE} bytes"))"

# ---- cleanup old backups ----
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleaning backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -maxdepth 1 -name 'kojo_backup_*.dump' -mtime "+${RETENTION_DAYS}" -delete

OLD_COUNT=$(find "$BACKUP_DIR" -maxdepth 1 -name 'kojo_backup_*.dump' | wc -l)
DISK_USAGE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done. Backup files: ${OLD_COUNT}, disk usage: ${DISK_USAGE}"
