#!/usr/bin/env bash

# Prep script to run before test scripts: ensures the test dump is up-to-date
# (running `manage.py dump_test` if not) and cleans the test DB environment,
# mirroring scripts/test.sh's cleanup + database preparation steps.
set -euo pipefail

# Activate virtual environment if not already active
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  _venv_dir=""
  for _candidate in .venv venv; do
    if [[ -f "$_candidate/bin/activate" ]]; then
      _venv_dir="$_candidate"
      break
    fi
  done
  if [[ -z "$_venv_dir" ]]; then
    _venv_dir=$(find . -maxdepth 2 -type d -name "*venv*" 2>/dev/null | while read -r d; do
      [[ -f "$d/bin/activate" ]] && echo "$d" && break
    done | head -1)
  fi
  if [[ -n "$_venv_dir" ]]; then
    echo "==> Activating virtual environment: $_venv_dir"
    source "$_venv_dir/bin/activate"
  else
    echo "WARNING: No virtual environment found (searched *venv* dirs)" >&2
  fi
  unset _venv_dir _candidate
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SQL_FILE="${PROJECT_ROOT}/larpmanager/tests/test_db.sql"

get_dump_version() {
  tail -50 "$SQL_FILE" 2>/dev/null | grep -oP "LARPMANAGER_SCHEMA_VERSION:\s*\K\S+" || echo ""
}

get_latest_migration() {
  ls -1 "${PROJECT_ROOT}"/larpmanager/migrations/[0-9]*.py 2>/dev/null | sort -V | tail -1 | xargs -r basename -s .py
}

ensure_dump_up_to_date() {
  echo "==> Checking test dump schema version..."

  local dump_version latest_migration
  dump_version=$(get_dump_version)
  latest_migration=$(get_latest_migration)

  if [[ -z "$latest_migration" ]]; then
    echo "ERROR: Could not find migration files" >&2
    exit 1
  fi

  if [[ -n "$dump_version" && "$dump_version" == "$latest_migration" ]]; then
    echo "Schema version OK: $dump_version"
    return
  fi

  if [[ -z "$dump_version" ]]; then
    echo "Test dump has no schema version marker, regenerating..."
  else
    echo "Test dump is outdated (dump: $dump_version, latest: $latest_migration), regenerating..."
  fi

  ( cd "$PROJECT_ROOT" && python manage.py dump_test )

  dump_version=$(get_dump_version)
  latest_migration=$(get_latest_migration)
  if [[ "$dump_version" != "$latest_migration" ]]; then
    echo "ERROR: dump_test ran but schema version still does not match (dump: $dump_version, latest: $latest_migration)" >&2
    exit 1
  fi

  echo "Test dump regenerated: $dump_version"
}

cleanup_test_environment() {
  echo "==> Cleaning up test environment..."

  # Kill any running pytest and playwright processes (graceful first, then force)
  pkill -15 -f "pytest" 2>/dev/null || true
  pkill -15 -f "playwright" 2>/dev/null || true
  sleep 3
  pkill -9 -f "pytest" 2>/dev/null || true
  pkill -9 -f "playwright" 2>/dev/null || true
  sleep 1

  # Terminate all connections to test databases (including worker databases)
  PGPASSWORD="${PGPASSWORD:-larpmanager}" psql -U "${PGUSER:-larpmanager}" -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE (datname LIKE 'test_%' OR datname LIKE 'larp_test%')
      AND pid <> pg_backend_pid();
  " 2>/dev/null || true

  # Drop all test databases (including worker databases from previous runs)
  echo "Dropping all test databases..."
  for db in $(PGPASSWORD="${PGPASSWORD:-larpmanager}" psql -U "${PGUSER:-larpmanager}" -t -c "SELECT datname FROM pg_database WHERE datname LIKE 'test_%' OR datname LIKE 'larp_test%';" 2>/dev/null); do
    PGPASSWORD="${PGPASSWORD:-larpmanager}" psql -U "${PGUSER:-larpmanager}" -c "DROP DATABASE IF EXISTS \"$db\";" 2>/dev/null || true
  done

  # Clean pytest cache
  echo "Cleaning pytest cache..."
  rm -rf "${PROJECT_ROOT}/.pytest_cache"
  find "${PROJECT_ROOT}" -type d -name "__pycache__" -path "*/larpmanager/tests/*" -exec rm -rf {} + 2>/dev/null || true

  echo "Test environment cleaned successfully"
}

# Configuration
WORKERS="${1:-4}"
export WORKERS

echo "========================================"
echo "LarpManager Test Prep"
echo "========================================"
echo "Workers: $WORKERS"
echo ""

ensure_dump_up_to_date
echo ""

cleanup_test_environment
echo ""
