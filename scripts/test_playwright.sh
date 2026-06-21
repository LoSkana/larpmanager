#!/bin/bash

pytest -n "$WORKERS" --reruns-delay 5 larpmanager/tests/playwright
