#!/bin/bash

# pytest -n "$WORKERS" --reruns 5 --reruns-delay 2 --reuse-db --no-migrations -m e2e larpmanager/tests/playwright

# local
pytest -n "$WORKERS" --maxfail 1 --reruns-delay 2 --reuse-db --no-migrations -m e2e larpmanager/tests/playwright
