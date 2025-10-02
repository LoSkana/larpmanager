import os

from .base import *

SLUG_ASSOC = 'def'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'larpmanager',
        'USER': 'larpmanager',
        'PASSWORD': 'larpmanager',
        "HOST": os.getenv("DB_HOST", "localhost"),
        'PORT': '5432',
   }
}

name = os.getenv("POSTGRES_DB","larp_test")
worker = os.getenv("PYTEST_XDIST_WORKER")
if worker:
    name = f"{name}_{worker}"
    DATABASES["default"]["NAME"] = name

STATIC_ROOT = os.path.join(BASE_DIR, '../static')

COMPRESS_ENABLED = False

AUTO_BACKGROUND_TASKS = True

DEBUG = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
CELERY_TASK_ALWAYS_EAGER = True
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

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
        'level': 'WARN',
    },
}

FORMS_URLFIELD_ASSUME_HTTPS = True

ADMINS = [
    ('test', 'test@test.it')
]
