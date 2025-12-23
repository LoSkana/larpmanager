#!/bin/bash

# Run Playwright tests only in CI
if [[ "${CI:-false}" == "true" ]] || [[ "${GITHUB_ACTIONS:-false}" == "true" ]]; then
  pytest -n "$WORKERS" --reruns 5 --reruns-delay 2 larpmanager/tests/playwright
else
  pytest -n "$WORKERS" larpmanager/tests/playwright
fi
