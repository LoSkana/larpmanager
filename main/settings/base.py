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
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '0.0.0.0', 'larpmanager.localhost']

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
    'larpmanager.middleware.profiler.ProfilerMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'larpmanager.middleware.url.CorrectUrlMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'larpmanager.middleware.token.TokenAuthMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'larpmanager.middleware.exception.ExceptionHandlingMiddleware',
    'larpmanager.middleware.broken.BrokenLinkEmailsMiddleware',
    'larpmanager.middleware.locale.LocaleAdvMiddleware',
    'larpmanager.middleware.association.AssociationIdentifyMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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
                'larpmanager.utils.context.cache_association',
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

    'images_upload_url': '/upload_image/',
    'automatic_uploads': True,
    'file_picker_types': 'image',
    'paste_data_images': False,
}


TINYMCE_COMPRESSOR = False

SECURE_REFERRER_POLICY = 'origin'

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
    "delete from larpmanager_larpmanagerprofiler where created < CURRENT_DATE - INTERVAL '3 day';",
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
]

# PAYMENT SETTINGS
PAYMENT_SETTING_FOLDER = 'main/payment_settings/'

RECAPTCHA_PUBLIC_KEY = ''
RECAPTCHA_PRIVATE_KEY = ''

# max size of snippet
FIELD_SNIPPET_LIMIT = 150
