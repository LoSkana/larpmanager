#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
until nc -z db 5432; do
  sleep 1
done

[ -f main/settings/prod.py ] || cp main/settings/prod_example.py main/settings/prod.py

mkdir -p logs

echo "Update dependencies"
uv pip install --system -r pyproject.toml

echo "Migrations..."
python manage.py compilemessages
python manage.py migrate --noinput

echo "Static files..."
cd larpmanager/static
npm install
cd ../../
python manage.py collectstatic --noinput
python manage.py compress

echo "Initial data..."
cp -R larpmanager/tests/media/* media/
python manage.py import_features

echo "Start tasks..."
nohup python manage.py process_tasks > logs/background-tasks.log 2>&1 &

exec "$@"
