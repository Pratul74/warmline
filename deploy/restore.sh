#!/usr/bin/env bash
# Restores a dump into a NEW database, never over an existing one, then prints the row
# count of every table so the result can be checked.
# Usage: ./restore.sh <file.dump | s3://bucket/key.dump> <new_database_name>
# To bring a restored copy into production, follow the runbook (stop the api, rename the
# databases, start the api). This script never touches the live database.
set -euo pipefail
cd "$(dirname "$0")"

SOURCE="${1:-}"
TARGET="${2:-}"
if [ -z "$SOURCE" ] || [[ ! "$TARGET" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
    echo "usage: $0 <file.dump | s3://bucket/key.dump> <new_database_name (a-z, 0-9, _)>" >&2
    exit 2
fi

dump="$SOURCE"
if [[ "$SOURCE" == s3://* ]]; then
    dump="$(mktemp)"
    trap 'rm -f "$dump"' EXIT
    aws s3 cp --only-show-errors "$SOURCE" "$dump"
fi
[ -s "$dump" ] || { echo "dump file is missing or empty: $SOURCE" >&2; exit 1; }

# psql inside the db container, as the database owner. $1 is the target database.
db_psql() {
    local database="$1"; shift
    ./compose.sh exec -T db sh -c 'db="$1"; shift; psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" "$@"' sh "$database" "$@"
}

exists="$(db_psql postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$TARGET'" | tr -d '\r[:space:]')"
if [ "$exists" = "1" ]; then
    echo "database $TARGET already exists: choose a new name (this script never overwrites)" >&2
    exit 1
fi

db_psql postgres -c "CREATE DATABASE $TARGET"
./compose.sh exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --exit-on-error' sh "$TARGET" < "$dump"

echo "restored into $TARGET. Rows per table:"
db_psql "$TARGET" -tA -F ' ' -c "SELECT format('SELECT %L, count(*) FROM %I;', table_name, table_name) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name" | \
    db_psql "$TARGET" -tA -F ': '
