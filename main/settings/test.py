import os

from main.settings import BASE_DIR

SLUG_ASSOC = 'test'

DATABASES = {
    'default': {
        'ENGINE': 'dj_db_conn_pool.backends.postgresql',
        'NAME': 'larpmanager',
        'USER': 'larpmanager',
        'PASSWORD': 'larpmanager',
    }
}

STATIC_ROOT = os.path.join(BASE_DIR, '../static')

COMPRESS_ENABLED = False

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
