#!/usr/bin/env bash
set -euo pipefail

# create branch
git checkout -B deps/pip-upgrade

# create venv
rm -rf .test_venv
python -m venv .test_venv
. .test_venv/bin/activate
python -m pip install -U pip setuptools wheel

# baseline install
python -m pip install -r requirements.txt
python -m pip check || true

# upgrade packages
tmpfile=$(mktemp)
while read line; do
  pkg=$(echo "$line" | grep -Eo '^[A-Za-z0-9_.-]+')
  if [ -n "$pkg" ]; then
    ver=$(curl -s https://pypi.org/pypi/$pkg/json | jq -r .info.version 2>/dev/null)
    if [ "$ver" != "null" ] && [ -n "$ver" ]; then
      echo "$pkg==$ver"
    else
      echo "$line"
    fi
  else
    echo "$line"
  fi
done < requirements.txt > "$tmpfile" && mv "$tmpfile" requirements.txt

# reinstall packages
python -m pip install -r requirements.txt
python -m pip check || true

# DB env
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=larpmanager
export POSTGRES_PASSWORD=larpmanager
export POSTGRES_DB=larpmanager_test

export CI=true
export DB_HOST=localhost

python manage.py compilemessages
python manage.py collectstatic --noinput
python manage.py compress

playwright install

# tests
export WORKERS=12
bash scripts/create_dbs.sh "$WORKERS" larpmanager/tests/test_db.sql
bash scripts/test_unit.sh
bash scripts/test_playwright.sh
