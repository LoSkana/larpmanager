SLUG_ASSOC = 'test'

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

DEEPL_API_KEY = '???'

# CREATE DATABASE larpmanager;
# CREATE USER larpmanager WITH PASSWORD 'larpmanager';
# ALTER USER larpmanager CREATEDB;
# ALTER DATABASE larpmanager OWNER TO larpmanager;
# GRANT ALL PRIVILEGES ON DATABASE larpmanager TO larpmanager;
