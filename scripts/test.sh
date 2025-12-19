#!/usr/bin/env bash
# scripts/test.sh
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

# Configuration
WORKERS="${1:-6}"
export WORKERS

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

# Prepare databases
echo "==> Preparing test databases..."
bash "${SCRIPT_DIR}/create_dbs.sh" "$WORKERS" "$SQL_FILE"
echo ""

# Setup environment for tests
export PYTEST_CURRENT_TEST="true"
export HOME=$(mktemp -d)

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
