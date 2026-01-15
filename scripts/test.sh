#!/usr/bin/env bash

# Unified test script for LarpManager
set -euo pipefail

check_branch() {
  # Skip check if running in CI environment
  if [[ "${CI:-false}" == "true" ]] || [[ "${GITHUB_ACTIONS:-false}" == "true" ]]; then
    return 0
  fi

  # Get current git branch name
  local current_branch
  current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

  # Raise error if on main branch
  if [[ "$current_branch" == "main" ]]; then
    echo "ERROR: Tests cannot be executed while on 'main' branch" >&2
    echo "Please switch to a different branch or run in CI environment" >&2
    exit 1
  fi
}

check_schema_version() {
  local sql_file="$1"

  echo "==> Checking database schema version..."

  # Get schema version from SQL dump
  local dump_version
  dump_version=$(tail -50 "$sql_file" | grep -oP "LARPMANAGER_SCHEMA_VERSION:\s*\K\S+" || echo "")

  # Get latest migration file
  local latest_migration
  latest_migration=$(ls -1 larpmanager/migrations/[0-9]*.py 2>/dev/null | sort -V | tail -1 | xargs basename -s .py 2>/dev/null || echo "")

  if [[ -z "$dump_version" ]]; then
    echo "WARNING: Could not find schema version in $sql_file" >&2
    echo "The dump may be outdated. Run 'python manage.py dump_test' to update it." >&2
    return 1
  fi

  if [[ -z "$latest_migration" ]]; then
    echo "WARNING: Could not find migration files" >&2
    return 1
  fi

  if [[ "$dump_version" != "$latest_migration" ]]; then
    echo "ERROR: Database schema is outdated!" >&2
    echo "  Dump version:     $dump_version" >&2
    echo "  Latest migration: $latest_migration" >&2
    echo "" >&2
    echo "Please run: python manage.py dump_test" >&2
    exit 1
  fi

  echo "Schema version OK: $dump_version"
}

cleanup_test_environment() {
  echo "==> Cleaning up test environment..."

  # Kill any running pytest and playwright processes
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
  rm -rf .pytest_cache
  find . -type d -name "__pycache__" -path "*/larpmanager/tests/*" -exec rm -rf {} + 2>/dev/null || true

  echo "Test environment cleaned successfully"
}

# Configuration
WORKERS="${1:-4}"
export WORKERS

# Ensure playwright browsers are installed
python -m playwright install chromium 2>/dev/null || playwright install

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SQL_FILE="${PROJECT_ROOT}/larpmanager/tests/test_db.sql"

# Prevent running tests on main branch
check_branch

echo "========================================"
echo "LarpManager Test Suite"
echo "========================================"
echo "Workers: $WORKERS"
echo ""

# Check if database schema is up-to-date
check_schema_version "$SQL_FILE"
echo ""

# Clean up test environment before running tests
cleanup_test_environment
echo ""

# Prepare databases
echo "==> Preparing test databases..."
bash "${SCRIPT_DIR}/create_dbs.sh" "$WORKERS" "$SQL_FILE"
echo ""

# Setup environment for tests
export PYTEST_CURRENT_TEST="true"

# Run unit tests
echo "==> Running unit tests..."
bash "${SCRIPT_DIR}/test_unit.sh"
echo ""

# Run Playwright tests
echo "==> Running Playwright tests..."
bash "${SCRIPT_DIR}/test_playwright.sh"
echo ""

echo "========================================"
echo "All tests passed! ✓"
echo "========================================"
