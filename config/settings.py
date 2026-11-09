import os
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env', override=False)


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_csv(name, default=''):
    raw = os.environ.get(name, default).replace(';', ',')
    return [item.strip() for item in raw.split(',') if item.strip()]


def app_hostname(value):
    raw = (value or '').strip().rstrip('/')
    if not raw:
        return ''
    parsed = urlparse(raw if '://' in raw else f'https://{raw}')
    return (parsed.hostname or '').strip()



SECRET_KEY = (
    os.environ.get('SECRET_KEY')
    or os.environ.get('DJANGO_SECRET_KEY')
    or ''
).strip().strip("'\"")
DEBUG = env_bool('DEBUG', default=False)

if not SECRET_KEY:
    raise ImproperlyConfigured(
        'SECRET_KEY is missing. Set it in .env for local work, or in the PaaS environment for production.'
    )

ALLOWED_HOSTS = env_csv('ALLOWED_HOSTS', '127.0.0.1,localhost')
CSRF_TRUSTED_ORIGINS = [
    origin for origin in env_csv('CSRF_TRUSTED_ORIGINS')
    if origin.startswith(('http://', 'https://'))
]
app_url = os.environ.get('APP_URL', '').strip().rstrip('/')
app_host = app_hostname(app_url)
if app_host and app_host not in ALLOWED_HOSTS and '*' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(app_host)
if app_url.startswith(('http://', 'https://')) and app_url not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(app_url)
elif app_host:
    origin = f'https://{app_host}'
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)
for host in ALLOWED_HOSTS:
    if host in {'*', ''} or host.startswith('.'):
        continue
    origin = f'https://{host}'
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)



AUTH_USER_MODEL = 'marketplace.User'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'marketplace',
]

MIDDLEWARE = [
    'config.middleware.HealthCheckMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'marketplace.context_processors.site_nav',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'



DB_DIR = BASE_DIR / 'DB'
DB_DIR.mkdir(parents=True, exist_ok=True)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DB_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,
        },
    }
}


AUTH_PASSWORD_VALIDATORS = [

]


LANGUAGE_CODE = 'fa'

TIME_ZONE = 'Asia/Tehran'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': (
            'django.contrib.staticfiles.storage.StaticFilesStorage'
            if DEBUG
            else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
        ),
    },
}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', default=False)

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'

def env_text(name):
    return os.environ.get(name, '').strip().strip("'\"")


MELIPAYAMAK_USERNAME = env_text('MELIPAYAMAK_USERNAME')
MELIPAYAMAK_PASSWORD = env_text('MELIPAYAMAK_PASSWORD')
MELIPAYAMAK_FROM = env_text('MELIPAYAMAK_FROM')
MELIPAYAMAK_KEY = env_text('MELIPAYAMAK_KEY')


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
