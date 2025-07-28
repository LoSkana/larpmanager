import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = False

SLUG_ASSOC = 'larpmanager'

PAYPAL_TEST = False

SECRET_KEY = os.environ.get('SECRET_KEY')

ADMINS = [
  (os.environ.get('ADMIN_NAME'), os.environ.get('ADMIN_EMAIL')),
]

CONN_MAX_AGE = 60

DATABASES = {
    'default': {
        'ENGINE': 'dj_db_conn_pool.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASS'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': '5432',
   }
}

# Static & Media

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "../media")

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "../static")

COMPRESS_ROOT = STATIC_ROOT
COMPRESS_URL = STATIC_URL

# Social Account

SOCIALACCOUNT_ADAPTER = 'larpmanager.utils.auth.MySocialAccountAdapter'

AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin, regardless of `allauth`
    'larpmanager.utils.backend.EmailOrUsernameModelBackend',

    # `allauth` specific authentication methods, such as login by e-mail
    'allauth.account.auth_backends.AuthenticationBackend'
]

SITE_ID = 1

# Provider specific settings
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENTID', ''),
            'secret': os.environ.get('GOOGLE_SECRET', '')
        }, 'SCOPE': [
            'profile',
            'email',
        ], 'AUTH_PARAMS': {
            'access_type': 'online',
        },
    }
}

# CACHE - select2

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://redis:6379/1',
        'OPTIONS': {
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            'SOCKET_TIMEOUT': 5,
        },
        "TIMEOUT": 3600 * 24 * 15,

    },
    'select2': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://redis:6379/2',
        'OPTIONS': {
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            'SOCKET_TIMEOUT': 5,
        },
    },
}

SESSION_COOKIE_AGE = 3600 * 24 * 15

SESSION_SAVE_EVERY_REQUEST = True

SELECT2_CACHE_BACKEND = 'select2'

SESSION_ENGINE = "django.contrib.sessions.backends.cache"

# Optmistic imagekit to reduce cache load
IMAGEKIT_DEFAULT_CACHEFILE_STRATEGY = 'imagekit.cachefiles.strategies.Optimistic'


# Configurazione del logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': 'error.log',
            'formatter': 'verbose',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = ['http://larpmanager.cpularp.com', 'http://35.93.208.16', 'http://localhost:8264', 'http://127.0.0.1:8264']
RATELIMIT_IP_META_KEY = 'HTTP_X_FORWARDED_FOR'

# captcha
RECAPTCHA_PUBLIC_KEY = os.environ.get('RECAPTCHA_PUBLIC', '')
RECAPTCHA_PRIVATE_KEY = os.environ.get('RECAPTCHA_PRIVATE', '')
