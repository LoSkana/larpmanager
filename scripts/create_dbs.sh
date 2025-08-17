#!/usr/bin/env bash
# scripts/create_test_dbs.sh
set -euo pipefail

: "${POSTGRES_HOST:=localhost}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_USER:=larp}"
: "${POSTGRES_PASSWORD:=larp}"
: "${POSTGRES_DB:=larp_test}"
WORKERS="${1:-${WORKERS:-4}}"

export PGPASSWORD="${POSTGRES_PASSWORD}"
export PGHOST="${POSTGRES_HOST}"
export PGPORT="${POSTGRES_PORT}"
export PGUSER="${POSTGRES_USER}"

SQL_FILE="${2:-test_db.sql}"
if [ ! -f "$SQL_FILE" ]; then
  echo "Missing $SQL_FILE" >&2
  exit 1
fi

for i in $(seq 0 $((WORKERS-1))); do
  DB="${POSTGRES_DB}_gw${i}"
  echo "Recreating $DB"
  psql -v ON_ERROR_STOP=1 -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB}' AND pid <> pg_backend_pid();" || true
  psql -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE IF EXISTS ${DB};"
  psql -v ON_ERROR_STOP=1 -d postgres -c "CREATE DATABASE ${DB} OWNER ${POSTGRES_USER};"
  psql -v ON_ERROR_STOP=1 -d "${DB}" -c "SET search_path TO public;"
  psql -v ON_ERROR_STOP=1 -d "${DB}" -f "${SQL_FILE}" --quiet
done

echo "Done."
