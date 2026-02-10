from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY
SECRET_KEY = 'django-insecure-ymob%9c8jb8=ld@^f(*(sc-)m7i=zgvcn6c+k85l7s5m@&hce('
DEBUG = False

# 2. Allow local host (Required when DEBUG is False)
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']


# APPLICATIONS
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'django_bootstrap5',
    'rest_framework',
    'captcha',

    # Your Apps
    # 'user',
    'website',   # ← teammate app added
]


# MIDDLEWARE
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # Teammate middleware
    'website.middleware.DynamicTranslationMiddleware',
]


ROOT_URLCONF = 'core.urls'
WSGI_APPLICATION = 'core.wsgi.application'


# TEMPLATES
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

                # Your custom context processor
                'website.context_processors.global_settings',
            ],
        },
    },
]


# DATABASE
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,
        },
    }
}


# PASSWORD VALIDATION (Combined both)
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


# INTERNATIONALIZATION
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True
USE_TZ = True


# STATIC FILES
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']


# AUTH SETTINGS
AUTH_USER_MODEL = 'website.CustomUser'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'


# EMAIL CONFIG
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')


# CSRF / SECURITY
CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000',
    'http://localhost:8000'
]

CSRF_FAILURE_VIEW = 'website.views.csrf_failure'
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False


# CACHE (Keeping your DB cache instead of locmem)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'my_translation_cache',
    }
}


# CAPTCHA
CAPTCHA_CHALLENGE_FUNCT = 'captcha.helpers.random_char_challenge'
CAPTCHA_IMAGE_SIZE = (150, 50)
CAPTCHA_FONT_SIZE = 30
CAPTCHA_LENGTH = 6
CAPTCHA_OUTPUT_FORMAT = (
    '<img src="%(image_url)s" alt="captcha" class="captcha" /> '
    '<a href="%(audio_url)s" class="captcha-audio-btn text-info ms-2">'
    '<i class="bi bi-volume-up-fill" style="font-size: 1.5rem;"></i>'
    '</a> '
    '<button type="button" class="js-captcha-refresh btn btn-sm btn-outline-secondary ms-2">'
    '<i class="bi bi-arrow-clockwise"></i>'
    '</button>'
    '<br>%(hidden_field)s %(text_field)s'
)


# ENCRYPTION
ENCRYPTION_KEY = 'EOxZWt1RC6O9GKhF8d30FUxyCyjGAz29smC5i8tWA0I='
CSRF_FAILURE_VIEW = 'website.views.csrf_failure'
