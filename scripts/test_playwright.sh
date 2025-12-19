#!/bin/bash

pytest -n "$WORKERS" larpmanager/tests/playwright

# local
#pytest -n "$WORKERS" --maxfail 1 --reruns-delay 2 larpmanager/tests/playwright
