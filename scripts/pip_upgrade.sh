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

# upgrade in place
python -m pip install --upgrade --upgrade-strategy eager -r requirements.txt
python -m pip check || true
python -m pip install -q pipdeptree || true
pipdeptree --warn fail || true

# rewrite requirements.txt with same lines but pinned to installed versions
python - <<'PY'
import re, sys
from pathlib import Path
from importlib.metadata import version, PackageNotFoundError

req_path = Path("requirements.txt")
orig = req_path.read_text(encoding="utf-8").splitlines()

name_re = re.compile(r"""
    ^\s*
    (?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)
    (?P<extras>\[[^\]]+\])?
    \s*
    (?P<spec>(?:==|>=|<=|>|<|~=|!=).*)?
    (?P<trailer>\s*;[^\#]+)?     # environment marker
    (?P<comment>\s*\#.*)?        # comment
    \s*$
""", re.VERBOSE)

out_lines = []
for line in orig:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        out_lines.append(line)
        continue

    m = name_re.match(line)
    if not m:
        out_lines.append(line)
        continue

    name = m.group("name")
    extras = m.group("extras") or ""
    trailer = m.group("trailer") or ""
    comment = m.group("comment") or ""

    try:
        ver = version(name)
    except PackageNotFoundError:
        out_lines.append(line)
        continue

    new_line = f"{name}{extras}=={ver}{trailer}{comment}"
    out_lines.append(new_line)

req_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
PY

# DB env
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=larpmanager
export POSTGRES_PASSWORD=larpmanager
export POSTGRES_DB=larpmanager_test

# tests
WORKERS=6
bash scripts/create_dbs.sh "$WORKERS" larpmanager/tests/test_db.sql
CI=true pytest -n "$WORKERS" --reruns 5 --reruns-delay 2 --reuse-db --no-migrations
