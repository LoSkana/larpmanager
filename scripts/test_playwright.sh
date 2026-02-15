#!/bin/bash

pytest -x -n "$WORKERS" --reruns 3 --reruns-delay 5 larpmanager/tests/playwright
