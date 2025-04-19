import os

from main.settings import BASE_DIR

SLUG_ASSOC = 'test'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'test_db',
        'USER': 'test',
        'PASSWORD': 'password',
        'HOST': 'postgres',
        'PORT': '5432',
    }
}

STATIC_ROOT = os.path.join(BASE_DIR, '../static')

COMPRESS_ENABLED = True

AUTO_BACKGROUND_TASKS = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}

# CREATE DATABASE larpmanager;
# CREATE USER larpmanager WITH PASSWORD 'larpmanager';
# ALTER USER larpmanager CREATEDB;
# ALTER DATABASE larpmanager OWNER TO larpmanager;
# GRANT ALL PRIVILEGES ON DATABASE larpmanager TO larpmanager;
