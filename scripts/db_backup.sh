#!/bin/bash
set -euo pipefail

set -a
source .env
set +a

DATE=$(date +"%Y-%m-%d_%H-%M")
BACKUP_NAME="db_backup_$DATE.sql.gz"
BACKUP_DIR="backups/"
REMOTE_PATH="HETZNER:$HETZNER_BUCKET/backups"

export RCLONE_CONFIG_HETZNER_TYPE=s3
export RCLONE_CONFIG_HETZNER_PROVIDER=Other
export RCLONE_CONFIG_HETZNER_ENDPOINT="$HETZNER_ENDPOINT"
export RCLONE_CONFIG_HETZNER_ACCESS_KEY_ID="$HETZNER_KEY"
export RCLONE_CONFIG_HETZNER_SECRET_ACCESS_KEY="$HETZNER_SECRET"
export RCLONE_CONFIG_HETZNER_ACL=private

mkdir -p "$BACKUP_DIR"

docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "postgres" \
    pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$BACKUP_DIR/$BACKUP_NAME"

rclone copy "$BACKUP_DIR/$BACKUP_NAME" "$REMOTE_PATH"

find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +7 -delete

rclone delete --min-age 90d "$REMOTE_PATH"
rclone rmdirs --leave-root "$REMOTE_PATH" 2>/dev/null || true

echo "Backup completed!"
