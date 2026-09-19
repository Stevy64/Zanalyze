"""
Django settings for Zanalyze (dev local + prod VPS).
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Charge .env sans dépendance obligatoire (python-dotenv si présent)."""
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=False)
        return
    except ImportError:
        pass
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, val = line.partition('=')
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv(BASE_DIR / '.env')


def _env_bool(name: str, default: str = '0') -> bool:
    return os.environ.get(name, default).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_list(name: str, default: str = '') -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(',') if x.strip()]


SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-0d6$0)t=a8h65hx-pe!+hky#4w=em41!6p__ebjw=2kyxv44hk',
)

DEBUG = _env_bool('DJANGO_DEBUG', '1')

ALLOWED_HOSTS = _env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')

# Derrière nginx (TLS terminé au reverse-proxy).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

if not DEBUG:
    if SECRET_KEY.startswith('django-insecure-'):
        raise RuntimeError(
            'DJANGO_SECRET_KEY doit être défini en production (DEBUG=0).'
        )
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = False  # lecture JS (header CSRF)

    ssl_on = _env_bool('DJANGO_SSL', '1')
    SESSION_COOKIE_SECURE = ssl_on
    CSRF_COOKIE_SECURE = ssl_on
    SECURE_SSL_REDIRECT = ssl_on and _env_bool('DJANGO_SECURE_SSL_REDIRECT', '1')
    if ssl_on:
        SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '31536000'))
        SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('DJANGO_HSTS_SUBDOMAINS', '0')
        SECURE_HSTS_PRELOAD = _env_bool('DJANGO_HSTS_PRELOAD', '0')

CSRF_TRUSTED_ORIGINS = _env_list('DJANGO_CSRF_TRUSTED_ORIGINS')
if not CSRF_TRUSTED_ORIGINS and not DEBUG:
    scheme = 'https' if _env_bool('DJANGO_SSL', '1') else 'http'
    CSRF_TRUSTED_ORIGINS = [
        f'{scheme}://{h}' for h in ALLOWED_HOSTS
        if h not in ('localhost', '127.0.0.1') and '*' not in h
    ]


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'paris.apps.ParisConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.http.ConditionalGetMiddleware',
    'paris.middleware.AnalyticsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# SQLite par défaut ; Postgres via DJANGO_DB_URL=postgres://user:pass@host:5432/db
_db_url = os.environ.get('DJANGO_DB_URL', '').strip()
if _db_url.startswith(('postgres://', 'postgresql://')):
    # postgres://user:pass@host:port/name
    import urllib.parse as _urlparse
    u = _urlparse.urlparse(_db_url)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': (u.path or '/').lstrip('/') or 'zanalyz',
            'USER': u.username or '',
            'PASSWORD': u.password or '',
            'HOST': u.hostname or '',
            'PORT': str(u.port or ''),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.environ.get('DJANGO_SQLITE_PATH', str(BASE_DIR / 'db.sqlite3')),
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

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
        'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
    },
}

# Microservice moteur (vide = calcul local dans le process Django)
# ZANALYZ_* prioritaire ; C2B_* conservé en secours pour les anciens déploiements.
def _env_first(*keys: str, default: str = '') -> str:
    for key in keys:
        value = os.environ.get(key, '').strip()
        if value:
            return value
    return default


ZANALYZ_MOTEUR_URL = _env_first('ZANALYZ_MOTEUR_URL', 'C2B_MOTEUR_URL')
ZANALYZ_REDIS_URL = _env_first('ZANALYZ_REDIS_URL', 'C2B_REDIS_URL')
# Snapshot Engine (défaut = raw GitHub Actions). Vide = DEFAULT dans engine_sync.
ZANALYZ_SNAPSHOT_URL = _env_first(
    'ZANALYZ_SNAPSHOT_URL',
    default='https://raw.githubusercontent.com/Stevy64/Zanalyze-Engine/main/exports/matchs.json',
)
ZANALYZ_SYNC_LIVE = _env_first('ZANALYZ_SYNC_LIVE', default='1')
# Alias rétrocompat (imports / scripts externes éventuels)
C2B_MOTEUR_URL = ZANALYZ_MOTEUR_URL
C2B_REDIS_URL = ZANALYZ_REDIS_URL
