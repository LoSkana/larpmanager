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

cleanup_test_environment() {
  echo "==> Cleaning up test environment..."

  # Kill any running pytest processes
  pkill -f "pytest" 2>/dev/null || true

  # Terminate all connections to test database
  PGPASSWORD="${PGPASSWORD:-larpmanager}" psql -U "${PGUSER:-larpmanager}" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'test_larpmanager' AND pid <> pg_backend_pid();" 2>/dev/null || true

  # Drop and recreate test database
  PGPASSWORD="${PGPASSWORD:-larpmanager}" psql -U "${PGUSER:-larpmanager}" -c "DROP DATABASE IF EXISTS test_larpmanager;" 2>/dev/null || true
  PGPASSWORD="${PGPASSWORD:-larpmanager}" psql -U "${PGUSER:-larpmanager}" -c "CREATE DATABASE test_larpmanager;" 2>/dev/null || true

  echo "Test environment cleaned successfully"
}

# Configuration
WORKERS="${1:-6}"
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
