#!/bin/bash
# Daily PostgreSQL backup — run via cron or Railway cron job
set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/tmp/investmcp_backup_${TIMESTAMP}.sql"

pg_dump "$DATABASE_URL" > "$BACKUP_FILE"
echo "Backup created: $BACKUP_FILE"
