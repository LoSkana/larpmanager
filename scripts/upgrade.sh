#!/bin/bash

BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [ "$BRANCH" == "main" ]; then
    echo "Errore: You are on branch main!" >&2
    exit 1
fi

# updates local references, removes deleted remote branches
git fetch --prune

# delete local branches fully merged in origin main
git branch --merged origin/main | grep -Ev "^\*?\s*(main|main|staging)$" | xargs git branch -d

git add -A && git commit

git checkout main && git pull

git checkout $BRANCH && git merge main

if [ -z "$VIRTUAL_ENV" ]; then
    source venv/bin/activate
fi

python manage.py makemigrations

git add -A
git commit -m "migrations"

./scripts/translate.sh

git add -A
git commit -m "locale"

git push origin $BRANCH

git checkout main
