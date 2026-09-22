#!/usr/bin/env bash
set -euo pipefail

# create branch
git checkout -B "deps/uv-upgrade-$(date +%Y%m%d)"

# Install uv if not present
if ! command -v uv &> /dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# create venv with uv
rm -rf .test_venv
uv venv .test_venv
. .test_venv/bin/activate

# drop exact pins so the resolver is free to pick latest versions
cp pyproject.toml pyproject.toml.bak
sed -i -E 's/==[^"]*"/"/g' pyproject.toml

# baseline install
uv pip install -r pyproject.toml

# upgrade all packages to latest versions
uv pip install --upgrade -r pyproject.toml

# restore original file, then write back the newly resolved versions as pins
mv pyproject.toml.bak pyproject.toml
uv pip freeze | grep -v '^-e' | while read line; do
  pkg=$(echo "$line" | cut -d'=' -f1)
  ver=$(echo "$line" | cut -d'=' -f3)
  if [ -n "$pkg" ] && [ -n "$ver" ]; then
    # Update version in pyproject.toml, preserving extras like "qrcode[pil]"
    sed -i -E "s|\"$pkg(\[[^]]*\])?==[^\"]*\"|\"$pkg\1==$ver\"|g" pyproject.toml
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

# npm dependencies (larpmanager/static/package.json) are not auto-upgraded here:
# several packages (the datatables.net-* family in particular) are pinned to
# versions that must stay in lockstep with each other's peer dependencies, so
# bumping them needs a manual look rather than a blind `npm update`.
# To upgrade: edit larpmanager/static/package.json by hand, then run
# `npm install` (or `npm outdated` first to see what's behind) inside
# larpmanager/static, and re-check the datatables.net-* set together.
echo "MANUAL STEP: review/upgrade npm packages in larpmanager/static/package.json (see comment above), then run 'npm install' there."
(cd larpmanager/static && npm install && npm update)

python manage.py compilemessages
python manage.py collectstatic --noinput
python manage.py compress

playwright install

# tests
export WORKERS=6
bash scripts/create_dbs.sh "$WORKERS" larpmanager/tests/test_db.sql
bash scripts/test_unit.sh
bash scripts/test_playwright.sh
