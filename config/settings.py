"""Settings for Chawanikwa Found It.

All environment-specific values come from environment variables (or a local
.env file in development). No real secrets live in this file.
"""
import os
import sys
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
TESTING = "test" in sys.argv

# --- Secret key -------------------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY:
    if DEBUG or TESTING:
        SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production-000000000"
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is not set. Generate one and put it in your environment."
        )
elif not (DEBUG or TESTING) and len(SECRET_KEY) < 40:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is too short for production (use 50+ characters).")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
if not (DEBUG or TESTING) and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# --- Railway (no-ops elsewhere) ---------------------------------------------
_railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
if _railway_domain:
    ALLOWED_HOSTS += [_railway_domain, "healthcheck.railway.app"]
    CSRF_TRUSTED_ORIGINS += [f"https://{_railway_domain}"]

TRUST_PROXY = env_bool("TRUST_PROXY", False)

# --- Apps -------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "reports",
    "search",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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
                "config.context.site",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------
_database_url = os.environ.get("DATABASE_URL", "").strip() or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {
    "default": dj_database_url.parse(_database_url, conn_max_age=60, conn_health_checks=True)
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cache (used for rate limiting) -----------------------------------------
if os.environ.get("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.environ["REDIS_URL"],
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# (max requests, window in seconds) per client IP
THROTTLES = {
    "search": (40, 60),
    "submit": (8, 3600),
    "claim": (6, 3600),
    "login": (10, 600),
}

# --- Auth -------------------------------------------------------------------
if TESTING:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "/staff/login/"
LOGIN_REDIRECT_URL = "/staff/"
LOGOUT_REDIRECT_URL = "/"
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# --- i18n -------------------------------------------------------------------
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Harare"
USE_I18N = True
USE_TZ = True

# --- Static files -----------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
_static_backend = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
    if not DEBUG and not TESTING
    else "django.contrib.staticfiles.storage.StaticFilesStorage"
)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _static_backend},
}

# --- Security ---------------------------------------------------------------
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
if TRUST_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG and not TESTING:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]  # platform health checks use plain HTTP
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", 60 * 60 * 24 * 30))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

ADMIN_URL = os.environ.get("DJANGO_ADMIN_URL", "admin/").lstrip("/")
if not ADMIN_URL.endswith("/"):
    ADMIN_URL += "/"

# --- Site / retention -------------------------------------------------------
SITE_NAME = "Chawanikwa Found It"
SITE_CONTACT_EMAIL = os.environ.get("SITE_CONTACT_EMAIL", "")
SITE_CONTACT_PHONE = os.environ.get("SITE_CONTACT_PHONE", "")
RETENTION_DAYS_FOUND = int(os.environ.get("RETENTION_DAYS_FOUND", 90))
RETENTION_DAYS_LOST = int(os.environ.get("RETENTION_DAYS_LOST", 180))
RETENTION_DAYS_AUDIT = int(os.environ.get("RETENTION_DAYS_AUDIT", 365))

# --- Logging ----------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"std": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False}},
}
