DEBUG = False

PAYPAL_TEST = False

SECRET_KEY = '???'

ADMINS = [
  ('???', '???'),
]

MANAGERS = [
  ('???', '???'),
]

CONN_MAX_AGE = 60

DATABASES = {
    'default': {
        'ENGINE': 'dj_db_conn_pool.backends.postgresql',
        'NAME': '???',
        'USER': '???',
        'PASSWORD': '???',
        'HOST': '/var/run/postgresql/',
   }
}


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
            'client_id': '???',
            'secret': '???'
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
        'LOCATION': 'unix:///var/run/redis/redis-server.sock?db=1',
        'OPTIONS': {
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            'SOCKET_TIMEOUT': 5,
        },
        "TIMEOUT": 3600 * 24 * 15,

    },
    'select2': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'unix:///var/run/redis/redis-server.sock?db=2',
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
RATELIMIT_IP_META_KEY = 'HTTP_X_FORWARDED_FOR'

# captcha
RECAPTCHA_PUBLIC_KEY = '???'
RECAPTCHA_PRIVATE_KEY = '???'

SKIP_PROFILER = False
