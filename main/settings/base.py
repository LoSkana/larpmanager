"""
Django settings for main project.
"""

import os
import re
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'changeme'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# ALLOWED_HOSTS = ['.larpmanager.com']
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '0.0.0.0']

# Application definition
INSTALLED_APPS = [
    'larpmanager.apps.LarpManagerConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'django.contrib.humanize',
    # 'django.contrib.sites',
    'phonenumber_field',
    'tinymce',
    'django_select2',
    'admin_auto_filters',
    'paypal.standard.ipn',
    'imagekit',
    'corsheaders',
    'background_task',
    'safedelete',
    'colorfield',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'import_export',
    'compressor',
    'debug_toolbar',
    'django_recaptcha',
]

MIDDLEWARE = [
    # Profiling middleware first to track everything
    'larpmanager.middleware.profiler.ProfilerMiddleware',
    # CORS to set headers early
    'corsheaders.middleware.CorsMiddleware',
    # Security middleware
    'django.middleware.security.SecurityMiddleware',
    # Session middleware needed by auth
    'django.contrib.sessions.middleware.SessionMiddleware',
    # URL correction before other processing
    'larpmanager.middleware.url.CorrectUrlMiddleware',
    # Messages depends on sessions
    'django.contrib.messages.middleware.MessageMiddleware',
    # Token auth (login using social provider) - before standard auth
    'larpmanager.middleware.token.TokenAuthMiddleware',
    # Authentication (must be before anything that depends on request.user)
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # Custom middleware for exception handling and locale
    'larpmanager.middleware.exception.ExceptionHandlingMiddleware',
    'larpmanager.middleware.broken.BrokenLinkEmailsMiddleware',
    'larpmanager.middleware.locale.LocaleAdvMiddleware',
    'larpmanager.middleware.association.AssociationIdentifyMiddleware',
    'larpmanager.middleware.translation.AssociationTranslationMiddleware',
    # Debug toolbar
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    # Common middleware handles APPEND_SLASH - must be near the end
    'django.middleware.common.CommonMiddleware',
    # CSRF protection
    'django.middleware.csrf.CsrfViewMiddleware',
    # Clickjacking protection
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Account middleware last
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'main.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [str(BASE_DIR.joinpath('templates'))],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'larpmanager.utils.core.context_processors.cache_association',
            ],
        },
    },
]

WSGI_APPLICATION = 'main.wsgi.application'

# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization

LANGUAGE_CODE = 'en'

LANGUAGES = [
    ('en', 'English'),
    ('it', 'Italiano'),
    ('es', 'Español'),
    ('de', 'Deutsch'),
    ('fr', 'Français'),
    ('cs', 'Čeština'),
    ('pl', 'Polski'),
    ('nl', 'Nederlands'),
    ('nb', 'Norsk'),
    ('sv', 'Svenska'),
    # ('pt', 'Português'),
    # ('el', 'Ελληνικά'),
    # ('da', 'Dansk'),
    # ('fi', 'suomi'),
    # ('et', 'Eesti'),
    # ('uk', 'українська мова'),
    # ('bg', 'български език'),
    # ('hu', 'magyar nyelv'),
    # ('lt', 'lietuvių kalba'),
    # ('ru', 'русский язык'),
    # ('lv', 'latviešu valoda'),
    # ('ro', 'Daco-Romanian'),
    # ('sk', 'slovenčina'),
    # ('sl', 'slovenščina'),
    # ('tr', 'Türkçe'),
    # ('id', 'Bahasa Indonesia'),
    # ('ja', '日本語'),
    # ('ko', '한국어'),
    # ('zh', '汉语'),
]

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = False

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Static files (CSS, JavaScript, Images)

STATIC_URL = '/static/'

STATIC_ROOT = os.path.join(BASE_DIR, '../../static-prod')

MEDIA_URL = '/media/'

MEDIA_ROOT = os.path.join(BASE_DIR, '../../media')


# Tinymce
TINYMCE_JS_URL = 'node_modules/tinymce/tinymce.min.js'
TINYMCE_DEFAULT_CONFIG = {
    'width': '100%',
    'height': '15em',
    'plugins': 'lists advlist autosave fullscreen table image link code autoresize wordcount autolink accordion emoticons media searchreplace codesample anchor',
    'toolbar': 'undo redo | styleselect | bold italic fontsizeselect forecolor backcolor hr | alignleft aligncenter alignright alignjustify | outdent indent | numlist bullist | restoredraft searchreplace | fullscreen code wordcount | image media emoticons accordion codesample anchor',
    'menubar': 'file edit insert view format table link image tools help',
    'convert_urls': False,
    'content_style': 'p {margin: 0.2em} .marker { color: #006ce7 !important; font-weight: bold; }',
    'contextmenu': False,
    'license_key': 'gpl',
    'promotion': False,

    'automatic_uploads': True,
    'file_picker_types': 'image media',
    'paste_data_images': False,
}


TINYMCE_COMPRESSOR = False

SECURE_REFERRER_POLICY = 'origin'

# Demo user password (used for creating demo accounts)
DEMO_PASSWORD = 'pippo'

# Maximum file upload size (10MB for TinyMCE uploads)
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB in bytes

# Allowed file extensions for TinyMCE uploads
ALLOWED_UPLOAD_EXTENSIONS = {
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp',
    # Documents
    '.pdf', '.doc', '.docx', '.odt', '.txt',
    # Audio/Video
    '.mp3', '.mp4', '.webm', '.ogg', '.wav',
}

# Upload rate limiting settings
UPLOAD_RATE_LIMIT = 10  # Maximum uploads per time window
UPLOAD_RATE_WINDOW = 60  # Time window in seconds (1 minute)
UPLOAD_MAX_STORAGE_PER_USER = 100 * 1024 * 1024  # 100MB total per user

# MIME type validation for uploads
ALLOWED_MIME_TYPES = {
    # Images
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml', 'image/bmp',
    # Documents
    'application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.oasis.opendocument.text', 'text/plain',
    # Audio/Video
    'audio/mpeg', 'video/mp4', 'video/webm', 'audio/ogg', 'video/ogg', 'audio/wav', 'audio/wave',
}


# email

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

X_FRAME_OPTIONS = 'SAMEORIGIN'

DBBACKUP_STORAGE = 'django.core.files.storage.FileSystemStorage'
BACKUP_ROOT = os.path.join(BASE_DIR, '../../../backup')
DBBACKUP_STORAGE_OPTIONS = {'location': BACKUP_ROOT}

SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'

# safe delete
SAFE_DELETE_FIELD_NAME = 'deleted'

CLEAN_DB = [
    'VACUUM',
    "delete from larpmanager_textversion where created < CURRENT_DATE - INTERVAL '6 months';",
    "delete from larpmanager_log where created < CURRENT_DATE - INTERVAL '6 months';",
    # "delete from paypal_ipn where created < CURRENT_DATE - INTERVAL '6 months';",
    "delete from background_task where run_at < CURRENT_DATE - INTERVAL '7 day';",
    "delete from background_task_completedtask where run_at < CURRENT_DATE - INTERVAL '7 day';",
    "delete from larpmanager_paymentinvoice where deleted < CURRENT_DATE - INTERVAL '7 day';",
    "delete from larpmanager_shuttleservice where deleted < CURRENT_DATE - INTERVAL '7 day';",

    "delete from larpmanager_registrationchoice where deleted < CURRENT_DATE - INTERVAL '6 months';",
    "delete from larpmanager_registrationanswer where deleted < CURRENT_DATE - INTERVAL '6 months';",
    "delete from larpmanager_writingchoice where deleted < CURRENT_DATE - INTERVAL '6 months';",
    "delete from larpmanager_writinganswer where deleted < CURRENT_DATE - INTERVAL '6 months';",
    "delete from larpmanager_accountingitempayment where deleted < CURRENT_DATE - INTERVAL '6 months';",
    "delete from larpmanager_accountingitemtransaction where deleted < CURRENT_DATE - INTERVAL '6 months';",
    "delete from larpmanager_accountingitemdiscount where deleted < CURRENT_DATE - INTERVAL '6 months';",
    "delete from larpmanager_registrationcharacterrel where deleted < CURRENT_DATE - INTERVAL '6 months';",

    "delete from larpmanager_registrationchoice where reg_id in ( select id from larpmanager_registration where deleted < CURRENT_DATE - INTERVAL '6 months');",
    "delete from larpmanager_registrationanswer where reg_id in ( select id from larpmanager_registration where deleted < CURRENT_DATE - INTERVAL '6 months');",
    "delete from larpmanager_accountingitempayment where reg_id in ( select id from larpmanager_registration where deleted < CURRENT_DATE - INTERVAL '6 months');",
    "delete from larpmanager_accountingitemtransaction where reg_id in ( select id from larpmanager_registration where deleted < CURRENT_DATE - INTERVAL '6 months');",
    "delete from larpmanager_playerrelationship where reg_id in ( select id from larpmanager_registration where deleted < CURRENT_DATE - INTERVAL '6 months');",
    "delete from larpmanager_registrationcharacterrel where reg_id in ( select id from larpmanager_registration where deleted < CURRENT_DATE - INTERVAL '6 months');",
    "delete from larpmanager_registration where deleted < CURRENT_DATE - INTERVAL '6 months';",

    "delete from larpmanager_casting where deleted < CURRENT_DATE - INTERVAL '6 months';",
    "delete from larpmanager_relationship where deleted < CURRENT_DATE - INTERVAL '6 months';",
    "delete from larpmanager_larpmanagerprofiler where created < CURRENT_DATE - INTERVAL '6 months';",
]


DATETIME_INPUT_FORMATS = ['%Y-%m-%d %H:%M']

DATE_INPUT_FORMATS = ['%Y-%m-%d']

SELECT2_I18N_AVAILABLE_LANGUAGES = ['en']

# paypal

PAYPAL_BUY_BUTTON_IMAGE = 'https://www.paypalobjects.com/digitalassets/c/website/marketing/apac/C2/logos-buttons/44_Yellow_CheckOut_Pill_Button.png'

# compressor

COMPRESS_OFFLINE = True

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    # other finders..
    'compressor.finders.CompressorFinder',
)

# debug toolbar

DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': 'larpmanager.middleware.base.show_toolbar',
}

LOCALE_PATHS = ('larpmanager/locale',)

# ACCOUNT_ACTIVATION_DAYS = 7
LOGIN_URL = '/login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'

# PROFILING
MIN_DURATION_PROFILER = 1
IGNORABLE_PROFILER_URLS = [
    re.compile(r'/media'),
    re.compile(r'/admin'),
    re.compile(r'logout'),
    re.compile(r'xyz'),
    re.compile(r'accounts/google/login/callback'),
    re.compile(r'apple-touch-icon'),
]

# PAYMENT SETTINGS
PAYMENT_SETTING_FOLDER = 'main/payment_settings/'

RECAPTCHA_PUBLIC_KEY = ''
RECAPTCHA_PRIVATE_KEY = ''

# max size of snippet
FIELD_SNIPPET_LIMIT = 150

# Cache timeout settings
# Maximum cache duration: 1 day (86400 seconds)
CACHE_TIMEOUT_1_DAY = 86400

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {name} {module} {funcName} {lineno} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {name} {funcName}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'larpmanager': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'deepl': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security.DisallowedHost': {
            'handlers': [],
            'propagate': False,
        },
    },
}
