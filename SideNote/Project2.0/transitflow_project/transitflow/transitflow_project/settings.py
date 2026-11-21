"""
Django settings for transitflow_project project.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# PayHero Integration & .secrets Auto-loader
SECRETS_FILE = BASE_DIR / '.secrets'
PAYHERO_API_TOKEN = None
PAYHERO_CHANNEL_ID = '5870'
PAYHERO_API_USERNAME = None
PAYHERO_API_PASSWORD = None

if SECRETS_FILE.exists():
    import base64
    try:
        with open(SECRETS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip()
                if k == 'API_Token':
                    PAYHERO_API_TOKEN = v
                    raw_b64 = v.replace('Basic ', '').strip()
                    try:
                        decoded = base64.b64decode(raw_b64).decode('utf-8')
                        if ':' in decoded:
                            PAYHERO_API_USERNAME, PAYHERO_API_PASSWORD = decoded.split(':', 1)
                    except Exception:
                        pass
                elif k == 'ChannelID':
                    PAYHERO_CHANNEL_ID = v
    except Exception:
        pass

SECRET_KEY = 'django-insecure-transitflow-logistics-goods-in-transit-secret-key-2026'

DEBUG = True

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Custom transitflow apps
    'core.apps.CoreConfig',
    'logistics.apps.LogisticsConfig',
    'payments.apps.PaymentsConfig',
    'assistant.apps.AssistantConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.RoleSessionMiddleware',
]

ROOT_URLCONF = 'transitflow_project.urls'

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
                'core.context_processors.role_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'transitflow_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_USER_MODEL = 'core.User'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 4},
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Nairobi'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Auth URLs
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'portal_redirect'
LOGOUT_REDIRECT_URL = 'login'

# Session Configuration
# Roles can have different session lifespans managed by RoleSessionMiddleware
SESSION_COOKIE_NAME = 'transitflow_session'
SESSION_COOKIE_AGE = 86400  # Default 24 hours
SESSION_SAVE_EVERY_REQUEST = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
