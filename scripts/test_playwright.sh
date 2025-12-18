#!/bin/bash

pytest -n "$WORKERS" --reruns 5 --reruns-delay 2 larpmanager/tests/playwright

# local
#pytest -n "$WORKERS" --maxfail 1 --reruns-delay 2 larpmanager/tests/playwright
