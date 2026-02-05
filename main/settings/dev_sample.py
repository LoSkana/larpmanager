SLUG_ASSOC = 'def'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'larpmanager',
        'USER': 'larpmanager',
        'PASSWORD': 'larpmanager',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

DEBUG_TOOLBAR = False

DEEPL_API_KEY = '???'

# To enable Amazon SES for email sending (optional):
# AWS_SES_ACCESS_KEY_ID = 'your-access-key-id'
# AWS_SES_SECRET_ACCESS_KEY = 'your-secret-access-key'
# AWS_SES_REGION_NAME = 'us-east-1'

# CREATE DATABASE larpmanager;
# CREATE USER larpmanager WITH PASSWORD 'larpmanager';
# ALTER USER larpmanager CREATEDB;
# ALTER DATABASE larpmanager OWNER TO larpmanager;
# GRANT ALL PRIVILEGES ON DATABASE larpmanager TO larpmanager;

ADMINS = [
    ('test', 'test@test.it')
]
