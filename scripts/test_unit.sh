#!/bin/bash

pytest -n "$WORKERS" --reuse-db --no-migrations larpmanager/tests/unit
