#!/bin/bash

# -----------------------------------------------------------------------------
# Encrypted backups (age)
# -----------------------------------------------------------------------------
# Backups are encrypted with age and end in ".sql.gz.age". The private key is 
# intentionally NOT kept on this host.
#
# One-time: create a keypair on a secure machine (NOT the backup host):
#   age-keygen -o identity.txt
#     - it prints the PUBLIC key (age1...) -> put that in .env as AGE_RECIPIENT
#     - identity.txt holds the SECRET key  -> store it offline (password manager,
#       vault, or USB). Anyone with it can read every backup; lose it and the
#       backups are unrecoverable.
#
# Restore: decrypt the .age file into backups/ as a plain .sql.gz, then re-run
# this script and pick it from the menu:
#   age -d -i identity.txt backups/db_backup_2026-05-31_20-14.sql.gz.age \
#       > backups/db_backup_2026-05-31_20-14.sql.gz
# -----------------------------------------------------------------------------

set -euo pipefail

set -a
source .env
set +a

if ! command -v age >/dev/null 2>&1; then
    echo "ERROR: 'age' is not installed; cannot encrypt backup." >&2
    exit 1
fi
if [ -z "${AGE_RECIPIENT:-}" ]; then
    echo "ERROR: AGE_RECIPIENT is not set in .env; refusing to write an unencrypted backup." >&2
    exit 1
fi

DATE=$(date +"%Y-%m-%d_%H-%M")
BACKUP_NAME="db_backup_$DATE.sql.gz.age"
BACKUP_DIR="backups/"
REMOTE_PATH="HETZNER:$HETZNER_BUCKET/backups"

export RCLONE_CONFIG_HETZNER_TYPE=s3
export RCLONE_CONFIG_HETZNER_PROVIDER=Hetzner
export RCLONE_CONFIG_HETZNER_ENDPOINT="$HETZNER_ENDPOINT"
export RCLONE_CONFIG_HETZNER_ACCESS_KEY_ID="$HETZNER_KEY"
export RCLONE_CONFIG_HETZNER_SECRET_ACCESS_KEY="$HETZNER_SECRET"
export RCLONE_CONFIG_HETZNER_NO_CHECK_BUCKET=true
export RCLONE_CONFIG_HETZNER_REGION="$HETZNER_REGION"
export RCLONE_CONFIG_HETZNER_ACL=private

mkdir -p "$BACKUP_DIR"

# pg_dump streams through gzip and age; plaintext never touches disk or Hetzner.
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "postgres" \
    pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
    | gzip \
    | age -r "$AGE_RECIPIENT" \
    > "$BACKUP_DIR/$BACKUP_NAME"

rclone copy "$BACKUP_DIR/$BACKUP_NAME" "$REMOTE_PATH"

find "$BACKUP_DIR" -type f -name "*.sql.gz*" -mtime +7 -delete

rclone delete --min-age 90d "$REMOTE_PATH"
rclone rmdirs --leave-root "$REMOTE_PATH" 2>/dev/null || true

echo "Backup completed!"
