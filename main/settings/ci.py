import os

from main.settings import BASE_DIR

#SLUG_ASSOC = 'def'
SLUB_ASSOC = 'larpmanager'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'larpmanager',
        'USER': 'larpmanager',
        'PASSWORD': 'larpmanager',
        "HOST": os.getenv("DB_HOST", "postgres"),
        'PORT': '5432',
        'TEST': {
            'NAME': 'test_larpmanager',
        },
   }
}

name = os.getenv("POSTGRES_DB","larp_test")
worker = os.getenv("PYTEST_XDIST_WORKER")
if worker:
    name = f"{name}_{worker}"
    DATABASES["default"]["NAME"] = name
    DATABASES["default"]["TEST"] = {"NAME": name}

STATIC_ROOT = os.path.join(BASE_DIR, '../static')

COMPRESS_ENABLED = True

AUTO_BACKGROUND_TASKS = True

DEBUG = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
CELERY_TASK_ALWAYS_EAGER = True

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

FORMS_URLFIELD_ASSUME_HTTPS = True

ADMINS = [
    ('test', 'test@test.it')
]
