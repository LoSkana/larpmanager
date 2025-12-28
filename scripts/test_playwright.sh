#!/bin/bash

pytest -n "$WORKERS" larpmanager/tests/playwright
