#!/bin/bash

source ./scripts/venv.sh

# remove show from test
sed -i 's/page_start(\(.*\), *show=True)/page_start(\1)/' larpmanager/tests/*.py

# remove incorrectly generated
find . -name "*.html.py" -type f -delete

python scripts/prepare_trans.py

cd larpmanager

django-admin makemessages --all --no-location

# remove confusing translation indications
find . -type f -name "*.po" -exec sed -i '/^#|/d' {} +
find . -type f -name "*.po" -exec sed -i '/^#~/d' {} +
find . -type f -name "*.po" -exec sed -i '/^"POT-Creation-Date:/d' {} +

cd ..

python manage.py translate

cd larpmanager

# check all .po file
find . -name "*.po" | while read -r file; do
  msgfmt --check-format "$file" -o /dev/null || {
    echo "Error in translation $file"
    exit 1
  }
done

django-admin compilemessages

cd ..
