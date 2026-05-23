#!/bin/bash

set -a
source .env
set +a

BACKUP_NAME="db_backup_$DATE.sql.gz"
BACKUP_DIR="backups/"

echo "Available backups in ${BACKUP_DIR}:"
mapfile -t backups < <(find "${BACKUP_DIR}" -type f -name "*.sql.gz")
if [ ${#backups[@]} -eq 0 ]; then
    echo "No .sql.gz backups found in ${BACKUP_DIR}."
    exit 1
fi

for i in "${!backups[@]}"; do
    echo "  [$i] ${backups[$i]}"
done

read -p "Select a backup by number: " selection
backup_file="${backups[$selection]}"

if [ ! -f "$backup_file" ]; then
    echo "Invalid selection or file not found."
    exit 1
fi

echo "Dropping and recreating database '${POSTGRES_DB}'..."

if ! docker exec -i postgres psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS $POSTGRES_DB;"; then
    echo "Failed to drop database. Exiting."
    exit 1
fi

if ! docker exec -i postgres psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE $POSTGRES_DB;"; then
    echo "Failed to create database. Exiting."
    exit 1
fi

echo "Restoring from $backup_file..."
if ! gunzip -c "$backup_file" | docker exec -i postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"; then
    echo "Restore failed. Exiting."
    exit 1
fi

echo "Restoration completed!"