#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
until nc -z db 5432; do
  sleep 1
done

echo "Update pips"
export PATH="/venv/bin:$PATH"
pip install -r requirements.txt -q

echo "Migrations..."
python manage.py compilemessages
python manage.py makemigrations larpmanager
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

exec "$@"
