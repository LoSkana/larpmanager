#!/usr/bin/env bash
set -euo pipefail

# create branch
git checkout -B deps/uv-upgrade

# Install uv if not present
if ! command -v uv &> /dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# create venv with uv
rm -rf .test_venv
uv venv .test_venv
. .test_venv/bin/activate

# baseline install
uv pip install -r pyproject.toml

# upgrade all packages to latest versions
uv pip install --upgrade -r pyproject.toml

# Generate updated pyproject.toml with new versions
uv pip freeze | grep -v '^-e' | while read line; do
  pkg=$(echo "$line" | cut -d'=' -f1)
  ver=$(echo "$line" | cut -d'=' -f3)
  if [ -n "$pkg" ] && [ -n "$ver" ]; then
    # Update version in pyproject.toml
    sed -i "s|\"$pkg==.*\"|\"$pkg==$ver\"|g" pyproject.toml
  fi
done

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
