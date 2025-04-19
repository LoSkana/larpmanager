#!/bin/bash

# Check that we are not on the main branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" = "main" ]; then
  echo "ERROR: You are on the 'main' branch."
  exit 1
fi

# Check that we are not on the server associated with larpmanager.com
LARPMANAGER_IP=$(getent hosts larpmanager.com | awk '{ print $1 }')
CURRENT_IP=$(hostname -I | awk '{ print $1 }')

if [ "$LARPMANAGER_IP" = "$CURRENT_IP" ]; then
  echo "ERROR: This server matches the IP of larpmanager.com ($CURRENT_IP)."
  exit 1
fi

# Check that ENV environment variable is not set to 'prod'
if [ "${ENV,,}" = "prod" ]; then
  echo "ERROR: ENV environment variable is set to 'prod'."
  exit 1
fi

# reset db

if [[ -n "$VIRTUAL_ENV" ]]; then
    echo "Active virtual environment: $VIRTUAL_ENV"
else
    source venv/bin/activate
fi

python manage.py reset

cd larpmanager/static
npm install
cd ../..

if lsof -i :8000 >/dev/null; then
      echo "Port 8000 in use"
else
  # start server
  python manage.py runserver &

  echo "Waiting for server to start..."
  until curl --silent http://127.0.0.1:8000 > /dev/null; do
    sleep 0.5
  done
fi

# start recording

npx playwright codegen 127.0.0.1:8000  --target=python
