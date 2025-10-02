import os

from main.settings import BASE_DIR

SLUG_ASSOC = 'def'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'test_larpmanager',
        'USER': 'larpmanager',
        'PASSWORD': 'larpmanager',
        'HOST': 'localhost',
        'PORT': '5432',
   }
}

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
