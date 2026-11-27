#!/usr/bin/env bash
# Dumps the database (pg_dump custom format), checks the dump can be read, uploads it to
# S3 and keeps the newest local copies. Meant to run from cron as the deploy user.
# S3 access comes from the EC2 instance role: there are no AWS keys on the server.
set -euo pipefail
cd "$(dirname "$0")"
umask 077  # dump files readable by their owner only

BACKUP_DIR="${BACKUP_DIR:-/var/backups/warmline}"
KEEP_LOCAL="${KEEP_LOCAL:-7}"
S3_URI="$(sed -n 's/^BACKUP_S3_URI=//p' .env | tr -d '\r' | tail -n 1)"

mkdir -p "$BACKUP_DIR"
file="$BACKUP_DIR/warmline-$(date -u +%Y%m%dT%H%M%SZ).dump"

# Credentials stay inside the db container (its own environment), not on this command line.
./compose.sh exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$file.partial"
mv "$file.partial" "$file"

# A dump that pg_restore cannot list is useless: fail loudly now, not on restore day.
./compose.sh exec -T db pg_restore --list < "$file" > /dev/null

if [ -n "$S3_URI" ]; then
    aws s3 cp --only-show-errors "$file" "${S3_URI%/}/$(basename "$file")"
    echo "uploaded to ${S3_URI%/}/$(basename "$file")"
elif [ "${SKIP_UPLOAD:-0}" = "1" ]; then
    echo "SKIP_UPLOAD=1: local copy only"
else
    echo "BACKUP_S3_URI is empty in .env: the backup was NOT uploaded" >&2
    exit 1
fi

# Keep only the newest KEEP_LOCAL dumps on the disk (S3 keeps the rest; a lifecycle rule
# deletes old ones there).
ls -1t "$BACKUP_DIR"/warmline-*.dump | tail -n +"$((KEEP_LOCAL + 1))" | xargs -r rm --

echo "backup ok: $file ($(du -h "$file" | cut -f1))"
