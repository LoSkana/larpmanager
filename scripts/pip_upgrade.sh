#!/usr/bin/env bash
set -euo pipefail

# create branch
git checkout -B deps/pip-upgrade

# create venv
rm -rf .test_venv
python -m venv .test_venv
. .test_venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip check

# upgrade pip
python -m pip install -r requirements.txt --upgrade --upgrade-strategy eager
python -m pip freeze > requirements.txt
python -m pip check
pipdeptree --warn fail || true

export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=larpmanager
export POSTGRES_PASSWORD=larpmanager
export POSTGRES_DB=larpmanager_test

# launch tests
WORKERS=6
bash scripts/create_dbs.sh "$WORKERS" larpmanager/tests/test_db.sql
CI=true pytest -n "$WORKERS" --reruns 5 --reruns-delay 2 --reuse-db --no-migrations
