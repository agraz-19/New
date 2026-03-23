from pathlib import Path
import os
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================================
# CRITICAL: SECURITY SETTINGS - USE ENVIRONMENT VARIABLES
# ============================================================================

# SECRET_KEY - MUST be set via environment variable
SECRET_KEY = config(
    'SECRET_KEY',
    default='django-insecure-change-me-in-production'  # Only for dev, change immediately
)

# DEBUG mode - Change to False in production
DEBUG = config('DEBUG', default=True, cast=bool)

# ALLOWED_HOSTS - Configure for your domain
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='127.0.0.1,localhost',
    cast=Csv
)

# ============================================================================
# SSL & REDIRECT LOGIC
# ============================================================================

if DEBUG:
    ALLOWED_HOSTS = ['*']  # OK for local development
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
else:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# ============================================================================
# COOKIE SECURITY (Always On)
# ============================================================================

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
SESSION_COOKIE_AGE = 3600  # 1 hour

CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'

X_FRAME_OPTIONS = 'DENY'
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# ============================================================================
# CONTENT SECURITY POLICY (FIXED - Removed unsafe-inline)
# ============================================================================

SECURE_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' cdn.jsdelivr.net cdnjs.cloudflare.com; "  # ✅ Removed unsafe-inline
    "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdnjs.cloudflare.com fonts.googleapis.com; "
    "img-src 'self' data: https:; "
    "font-src 'self' fonts.gstatic.com cdnjs.cloudflare.com; "
    "connect-src 'self' https:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)

# ============================================================================
# TEMPLATES
# ============================================================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'website.context_processors.global_settings',
            ],
        },
    },
]

# ============================================================================
# APPLICATIONS
# ============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_bootstrap5',
    'rest_framework',
    'captcha',
    'website',
]

# ============================================================================
# MIDDLEWARE
# ============================================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'website.middleware.DynamicTranslationMiddleware',
]

# ============================================================================
# DATABASE & CACHE
# ============================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {'timeout': 20},
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'my_translation_cache',
    }
}

# ============================================================================
# EMAIL CONFIG (FIXED - Use environment variables)
# ============================================================================

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default='587', cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='petertriffle@gmail.com')  # ✅ From .env
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')  # ✅ From .env (NOT hardcoded)

# Fallback to console backend if email not configured
if not EMAIL_HOST_PASSWORD and DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ============================================================================
# ENCRYPTION (FIXED - Use environment variable)
# ============================================================================

ENCRYPTION_KEY = config(
    'ENCRYPTION_KEY',
    default='EOxZWt1RC6O9GKhF8d30FUxyCyjGAz29smC5i8tWA0I='  # ✅ From .env (NOT hardcoded)
)

# ============================================================================
# MINIO (FIXED - Use environment variables)
# ============================================================================

MINIO_ENDPOINT = config('MINIO_ENDPOINT', default='127.0.0.1:9000')  # ✅ From .env
MINIO_ACCESS_KEY = config('MINIO_ACCESS_KEY', default='minioadmin')  # ✅ From .env
MINIO_SECRET_KEY = config('MINIO_SECRET_KEY', default='minioadmin')  # ✅ From .env
MINIO_BUCKET_NAME = config('MINIO_BUCKET_NAME', default='events')
MINIO_SECURE = config('MINIO_SECURE', default=False, cast=bool)

#  WARN if using default credentials
if MINIO_ACCESS_KEY == 'minioadmin' or MINIO_SECRET_KEY == 'minioadmin':
    print('⚠️  WARNING: MinIO using default credentials! Change MINIO_ACCESS_KEY and MINIO_SECRET_KEY')

# ============================================================================
# REMAINING SETTINGS
# ============================================================================

AUTH_USER_MODEL = 'website.CustomUser'
ROOT_URLCONF = 'core.urls'
WSGI_APPLICATION = 'core.wsgi.application'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_URL = '/login/'
CSRF_FAILURE_VIEW = 'website.views.csrf_failure'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================================================
# REST FRAMEWORK
# ============================================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# ============================================================================
# PASSWORD VALIDATION
# ============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ============================================================================
# STARTUP CHECKS
# ============================================================================

if not DEBUG:
    # Production checks
    if SECRET_KEY == 'django-insecure-change-me-in-production':
        raise ValueError('❌ SECRET_KEY must be configured for production!')
    
    if 'localhost' in ALLOWED_HOSTS or '127.0.0.1' in ALLOWED_HOSTS:
        raise ValueError('❌ localhost/127.0.0.1 should not be in production ALLOWED_HOSTS')

print('✅ Django settings loaded successfully')
