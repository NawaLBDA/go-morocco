from pathlib import Path
from dotenv import load_dotenv
import os
import dj_database_url

# ==============================
# BASE
# ==============================
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-dev-key-change-later"
)

DEBUG = os.environ.get("DEBUG", "False") == "True"

# ✅ Dynamic ALLOWED_HOSTS based on environment
if os.environ.get("ENVIRONMENT") == "production":
    ALLOWED_HOSTS = [
        "go-morocco.onrender.com",
        "*.onrender.com",
        os.environ.get("CUSTOM_DOMAIN", ""),
    ]
else:
    ALLOWED_HOSTS = [
        "go-morocco.onrender.com",
        "localhost",
        "127.0.0.1",
        "*.local",
    ]

# ✅ CSRF Protection
CSRF_TRUSTED_ORIGINS = [
    "https://go-morocco.onrender.com",
    f"https://{os.environ.get('CUSTOM_DOMAIN', '')}",
]

# ==============================
# APPLICATIONS
# ==============================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Apps
    'apps.core.apps.CoreConfig',
    'apps.reservations',

    # Third-party
    'widget_tweaks',
    'cloudinary',
    'cloudinary_storage',
]

# ==============================
# MIDDLEWARE
# ==============================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ==============================
# URLS / TEMPLATES
# ==============================
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

WSGI_APPLICATION = 'travel_agency.wsgi.application'

# ==============================
# DATABASE (Render PostgreSQL)
# ==============================
DATABASE_URL = os.environ.get("DATABASE_URL")

ENVIRONMENT = os.environ.get("ENVIRONMENT", "local")

if ENVIRONMENT == "production" and os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.parse(
            os.environ.get("DATABASE_URL"),
            conn_max_age=600,
            ssl_require=True
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": "travel_agency",
            "USER": "root",
            "PASSWORD": "P@ss123",
            "HOST": "localhost",
            "PORT": "3306",
            "OPTIONS": {
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
                "charset": "utf8mb4",
            },
        }
    }

# ==============================
# AUTH
# ==============================
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'
LOGIN_URL = 'login'

# ==============================
# STATIC FILES
# ==============================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

# ==============================
# MEDIA / CLOUDINARY
# ==============================

DEFAULT_FILE_STORAGE = (
    "cloudinary_storage.storage.MediaCloudinaryStorage"
)

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.environ.get("CLOUDINARY_CLOUD_NAME"),
    "API_KEY": os.environ.get("CLOUDINARY_API_KEY"),
    "API_SECRET": os.environ.get("CLOUDINARY_API_SECRET"),
}
import cloudinary
import cloudinary.uploader
import cloudinary.api

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)
# ==============================
# STRIPE
# ==============================
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PUBLIC_KEY = os.environ.get("STRIPE_PUBLIC_KEY")

# ==============================
# DEFAULTS
# ==============================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==============================
# MESSAGES
# ==============================
from django.contrib.messages import constants as messages

MESSAGE_TAGS = {
    messages.SUCCESS: "success",
    messages.ERROR: "danger",
    messages.WARNING: "warning",
    messages.INFO: "info",
}

# ==============================
# 🚀 PERFORMANCE OPTIMIZATIONS
# ==============================

# ✅ Database Connection Pooling
DATABASES['default']['CONN_MAX_AGE'] = 600

# ✅ Caching (Redis-like or Local Memory)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-location',
        'TIMEOUT': 3600,  # 1 hour
        'OPTIONS': {
            'MAX_ENTRIES': 1000
        }
    }
}

# ✅ Session Management (Faster with Cache)
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 604800  # 1 week
SESSION_COOKIE_SECURE = True if os.environ.get("ENVIRONMENT") == "production" else False

# ✅ Template Caching
TEMPLATES[0]['OPTIONS']['loaders'] = [
    ('django.template.loaders.cached.Loader', [
        'django.template.loaders.filesystem.Loader',
        'django.template.loaders.app_directories.Loader',
    ]),
]

# ✅ Static Files Compression (WhiteNoise)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ✅ GZIP Compression for WhiteNoise
WHITENOISE_COMPRESS_OFFLINE = True
WHITENOISE_COMPRESS_ONLINE = True
WHITENOISE_SKIP_COMPRESS_ON_BROTLI = True

# ✅ Database Query Optimization
DEBUG_PROPAGATE_EXCEPTIONS = True

# ==============================
# 🔒 SECURITY HEADERS & SETTINGS
# ==============================

# ✅ HTTPS/SSL Settings (Production only)
if os.environ.get("ENVIRONMENT") == "production":
    # Force HTTPS
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    # HSTS (HTTP Strict Transport Security)
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    
    # Cookie Security
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    
    # Cookies SameSite
    CSRF_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Security Headers
    SECURE_CONTENT_SECURITY_POLICY = {
        'default-src': ("'self'",),
        'script-src': (
            "'self'",
            'cdn.jsdelivr.net',
            'cdnjs.cloudflare.com',
            "'unsafe-inline'",  # Remove if possible after testing
        ),
        'style-src': (
            "'self'",
            'cdn.jsdelivr.net',
            'cdnjs.cloudflare.com',
            "'unsafe-inline'",
        ),
        'img-src': (
            "'self'",
            'data:',
            'https:',
            'res.cloudinary.com',
        ),
        'font-src': (
            "'self'",
            'cdnjs.cloudflare.com',
            'data:',
        ),
    }
    
    # X-Frame-Options (Clickjacking protection)
    X_FRAME_OPTIONS = 'DENY'
    
    # X-Content-Type-Options (MIME type sniffing)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    
    # X-XSS-Protection
    SECURE_BROWSER_XSS_FILTER = True

# ✅ CSRF & XSS Protection (Always)
CSRF_FAILURE_VIEW = 'django.views.csrf.csrf_failure'

# ✅ Authentication Security
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,  # Minimum 8 characters
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ✅ Logging Security Errors
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'errors.log',
        },
        'console': {
            'level': 'WARNING',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# ✅ Django Security Middleware (Already enabled)
# MIDDLEWARE includes: SecurityMiddleware, XFrameOptionsMiddleware, etc.

# ==============================
# 📱 OPTIMIZATION SETTINGS
# ==============================

# ✅ Form validation
FORM_RENDERER = 'django.forms.renderers.TemplatesSafeRenderer'

# ✅ Minify HTML
MIDDLEWARE = MIDDLEWARE + [
    'django.middleware.common.CommonMiddleware',
]

# ✅ Email settings (Render supports SendGrid)
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.sendgrid.net')
EMAIL_HOST_USER = os.environ.get('SENDGRID_USERNAME', '')
EMAIL_HOST_PASSWORD = os.environ.get('SENDGRID_PASSWORD', '')
EMAIL_PORT = 587
EMAIL_USE_TLS = True

# ✅ API Rate Limiting (for future API endpoints)
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB

# ✅ Admin Security
ADMIN_URL = os.environ.get('ADMIN_URL', 'admin/')

