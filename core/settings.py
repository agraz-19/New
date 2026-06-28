from pathlib import Path
import os
import secrets
from decouple import config
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
  return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


# SECURITY
SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = False

# Keep this False while testing on HTTP.
# Set DJANGO_USE_HTTPS_SECURITY=true only when running behind HTTPS.
USE_HTTPS_SECURITY = env_bool("DJANGO_USE_HTTPS_SECURITY", False)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

#SECURE_SSL_REDIRECT = USE_HTTPS_SECURITY
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000")) if USE_HTTPS_SECURITY else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = USE_HTTPS_SECURITY
SECURE_HSTS_PRELOAD = USE_HTTPS_SECURITY

ALLOWED_HOSTS = ["10.160.19.20", "192.168.56.101", "127.0.0.1", "localhost","192.168.1.8"]

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
  origin.strip()
  for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
  if origin.strip()
]
CORS_ALLOW_CREDENTIALS = False


# APPLICATIONS
INSTALLED_APPS = [
  "django.contrib.admin",
  "django.contrib.auth",
  "django.contrib.contenttypes",
  "django.contrib.sessions",
  "django.contrib.messages",
  "whitenoise.runserver_nostatic",
  "django.contrib.staticfiles",

  "django_bootstrap5",
  "rest_framework",
  "captcha",

  "website",
]


# MIDDLEWARE
MIDDLEWARE = [
  "website.middleware.ErrorHandlingMiddleware",
  "website.middleware.StripUnnecessaryHeadersMiddleware",
  "website.middleware.SecurityHeadersMiddleware",
  "django.middleware.security.SecurityMiddleware",
  "whitenoise.middleware.WhiteNoiseMiddleware",
  "django.contrib.sessions.middleware.SessionMiddleware",
  "django.middleware.common.CommonMiddleware",
  "django.middleware.csrf.CsrfViewMiddleware",
  "django.contrib.auth.middleware.AuthenticationMiddleware",
  "django.contrib.messages.middleware.MessageMiddleware",
  "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"


CSRF_TRUSTED_ORIGINS = [
  "http://192.168.1.8:8000",
  "http://127.0.0.1:8000",
  "http://localhost:8000",
  "http://10.160.19.20:8000",
  "http://192.168.56.101:8000",
]


# TEMPLATES
TEMPLATES = [
  {
      "BACKEND": "django.template.backends.django.DjangoTemplates",
      "DIRS": [BASE_DIR / "templates"],
      "APP_DIRS": True,
      "OPTIONS": {
          "context_processors": [
              "django.template.context_processors.request",
              "django.contrib.auth.context_processors.auth",
              "django.contrib.messages.context_processors.messages",
              "website.context_processors.global_settings",
          ],
      },
  },
]


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
  {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
  {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
  {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
  {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# INTERNATIONALIZATION
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True


# STATIC FILES
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# MEDIA FILES
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"


# AUTH SETTINGS
AUTH_USER_MODEL = "website.CustomUser"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"


# EMAIL CONFIG
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")


# CSRF / SESSION / SECURITY
CSRF_FAILURE_VIEW = "website.views.csrf_failure"

CSRF_COOKIE_SECURE = USE_HTTPS_SECURITY
SESSION_COOKIE_SECURE = USE_HTTPS_SECURITY

# Keep False if your JS reads csrftoken from cookie.
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_AGE = None
CSRF_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True


# CACHE
CACHES = {
  "default": {
      "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
      "LOCATION": os.path.join(BASE_DIR, ".django_cache"),
  }
}


# CAPTCHA
CAPTCHA_IMAGE_SIZE = (160, 60)
CAPTCHA_FONT_SIZE = 32
CAPTCHA_FOREGROUND_COLOR = "#000000"
CAPTCHA_LETTER_ROTATION = (-15, 15)
CAPTCHA_LENGTH = 5
CAPTCHA_NOISE_FUNCTIONS = (
  "captcha.helpers.noise_arcs",
  "captcha.helpers.noise_dots",
)
CAPTCHA_CHALLENGE_FUNCT = "captcha.helpers.random_char_challenge"
CAPTCHA_FLITE_PATH = os.path.join(BASE_DIR, "espeak_wrapper.sh")


# ENCRYPTION
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

SESSION_EXPIRE_AT_BROWSER_CLOSE = True
# Configure CSRF cookie to be session-only by not setting a max-age
CSRF_COOKIE_AGE = None

# SameSite policy for cookies
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SAMESITE = 'Strict'
LANGUAGE_COOKIE_SAMESITE = 'Strict'

# Use cookie-backed messages and ensure its cookie uses SameSite=Strict
MESSAGE_STORAGE = 'django.contrib.messages.storage.cookie.CookieStorage'
try:
    import django.contrib.messages.storage.cookie as message_cookie
    # Enforce Strict SameSite, secure transport and HttpOnly on messages cookie
    message_cookie.CookieStorage.cookie_kwargs = {
        'samesite': 'Strict',
        'secure': True,
        'httponly': True,
    }
except Exception:
    # If message storage import fails, fall back to default storage without raising at import time
    pass

def AppScan_static_headers(headers, path, url):
  headers["Server"] = ""
  headers["Content-Security-Policy"] = "default-src 'self';"
  headers["X-Content-Type-Options"] = "nosniff"
  headers["Cross-Origin-Embedder-Policy"] = "require-corp"
  headers["Cross-Origin-Resource-Policy"] = "same-origin"
  headers["Access-Control-Allow-Origin"] = "*"
# Register the hook with WhiteNoise
WHITENOISE_ADD_HEADERS_FUNCTION = AppScan_static_headers    

LOGGING = {
  "version": 1,
  "disable_existing_loggers": False,
  "formatters": {
      "standard": {
          "format": "[{levelname}] {asctime} {name}: {message}",
          "style": "{",
      },
  },
  "handlers": {
      "console": {
          "class": "logging.StreamHandler",
          "formatter": "standard",
      },
  },
  "loggers": {
      "django.request": {
          "handlers": ["console"],
          "level": "ERROR",
          "propagate": False,
      },
      "website": {
          "handlers": ["console"],
          "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
          "propagate": False,
      },
  },
}