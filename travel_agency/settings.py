from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-dev-key-change-later'
DEBUG = True
ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.core.apps.CoreConfig',
    'apps.reservations',
    'widget_tweaks',

]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'travel_agency.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'apps.core.context_processors.sections_processor',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
STRIPE_SECRET_KEY = 'sk_test_51SpxfZ4YMQsgoNZ714OWYuDTtH4gfUQOrBt9fQ4NaolGxiwydO6OxdGM2qzxwM0W4C1xCyMTPTcYr7nMleU7dfoc00fggPuC2j'
STRIPE_PUBLIC_KEY = 'pk_test_51SpxfZ4YMQsgoNZ7pIlbVjDkCpGI49QCtLazSvXcx4fOZi3NcjR2MwdJGNjC7b3tlwJiz9UzfMendoL5toA2OYAv00t7GomWAM'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'travel_agency',   # ✅ base déjà créée
        'USER': 'root',
        'PASSWORD': 'P@ss123',
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}


STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# Authentication redirects
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'
LOGIN_URL = 'login'

# Message Tags
from django.contrib.messages import constants as messages
MESSAGE_TAGS = {
    messages.SUCCESS: 'success',
    messages.ERROR: 'danger',
    messages.WARNING: 'warning',
    messages.INFO: 'info',
}
