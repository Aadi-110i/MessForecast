"""
Django settings for the Meal Demand Forecasting and Food-Waste Reduction Platform.

Track P: Python + Django + PostgreSQL, forecasting in-process (Celery for scheduled work).

Every value that differs between a laptop and a server is read from the environment so the
same code runs in development, CI and production without edits.
"""

from pathlib import Path

import os
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key)
    return default if value is None or value == "" else value


def env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    "dev-only-insecure-key-change-me-in-production-0d6f1c9a2b7e4d8f3a5c0b9e2d7f4a1c6",
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.menu",
    "apps.attendance",
    "apps.events",
    "apps.demand",
    "apps.forecasting",
    "apps.planning",
    "apps.actuals",
    "apps.waste",
    "apps.reporting",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "apps.core.context_processors.platform_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database — PostgreSQL (Track P)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "messforecast"),
        "USER": env("POSTGRES_USER", "messforecast"),
        "PASSWORD": env("POSTGRES_PASSWORD", "messforecast_dev_pw"),
        "HOST": env("POSTGRES_HOST", "127.0.0.1"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(env("POSTGRES_CONN_MAX_AGE", "300")),
        "OPTIONS": {
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
        "TEST": {
            "NAME": env("POSTGRES_TEST_DB", "test_messforecast"),
        },
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "messforecast-default",
        "TIMEOUT": 60,
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.User"

# Where a successful sign-in lands. The default (``/accounts/profile/``) is a
# URL that this project does not serve, so it is pointed at the dashboard.
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# ---------------------------------------------------------------------------
# Internationalisation — campus in IST
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-in"
TIME_ZONE = env("DJANGO_TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files — WhiteNoise serves the PWA shell with cache headers
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
        # Versioned assets are cached hard; the service worker itself is served
        # through a view with no-cache headers (see pwa_urls.py).
        "WHITENOISE_MAX_AGE": 60 * 60 * 24 * 30,
    },
}
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30
WHITENOISE_MIMETYPES = {".js": "application/javascript", ".webmanifest": "application/manifest+json"}
WHITENOISE_ROOT = BASE_DIR / "static"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    # A delete that the schema refuses must come back as a 409 the client can
    # act on, not as a 500 that reads as a broken server.
    "EXCEPTION_HANDLER": "apps.api.exceptions.api_exception_handler",
    "DATETIME_FORMAT": "iso-8601",
}

# ---------------------------------------------------------------------------
# Simple JWT — bearer tokens for the API, session auth kept for the web app
# ---------------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(env("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", "15"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(env("JWT_REFRESH_TOKEN_LIFETIME_DAYS", "7"))
    ),
    "ROTATE_REFRESH_TOKENS": env_bool("JWT_ROTATE_REFRESH_TOKENS", True),
    "BLACKLIST_AFTER_ROTATION": env_bool("JWT_BLACKLIST_AFTER_ROTATION", True),
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SIGNING_KEY", SECRET_KEY),
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication.default_user_authentication_rule",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "SLIDING_TOKEN_LIFETIME": timedelta(minutes=5),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(days=1),
}

# ---------------------------------------------------------------------------
# Password reset email
#
# Console backend by default (development). Set DJANGO_EMAIL_BACKEND to an
# SMTP backend and supply the SMTP credentials to send real reset mail.
# ---------------------------------------------------------------------------
PASSWORD_RESET_TIMEOUT = int(env("PASSWORD_RESET_TIMEOUT_SECONDS", "3600"))
PASSWORD_RESET_FROM_EMAIL = env("PASSWORD_RESET_FROM_EMAIL", "mess-forecast@campus.example")

# ---------------------------------------------------------------------------
# Celery — Track P scheduled work (daily forecast + daily preparation guidance)
#
# A broker is optional for local development: without one, tasks run eagerly in
# the calling process so `manage.py` commands behave identically to production.
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "") or None
CELERY_TASK_ALWAYS_EAGER = not bool(CELERY_BROKER_URL)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "generate-daily-forecasts": {
        "task": "forecasting.tasks.generate_daily_forecasts",
        "schedule": float(env("CELERY_FORECAST_INTERVAL_SECONDS", "86400")),
    },
    "dispatch-preparation-guidance": {
        "task": "notifications.tasks.dispatch_preparation_guidance",
        "schedule": float(env("CELERY_GUIDANCE_INTERVAL_SECONDS", "86400")),
    },
    "flag-missing-actuals": {
        "task": "notifications.tasks.flag_missing_actuals",
        "schedule": float(env("CELERY_MISSING_ACTUALS_INTERVAL_SECONDS", "3600")),
    },
}

# ---------------------------------------------------------------------------
# Domain configuration
# ---------------------------------------------------------------------------
# Number of past weeks the baseline forecaster looks at.
FORECAST_LOOKBACK_WEEKS = int(env("FORECAST_LOOKBACK_WEEKS", "8"))
# Confidence level used for the published attendance interval.
FORECAST_CONFIDENCE_LEVEL = float(env("FORECAST_CONFIDENCE_LEVEL", "0.80"))
# Shortest history (in observations) before weekday/event effects are trusted.
FORECAST_MIN_OBSERVATIONS = int(env("FORECAST_MIN_OBSERVATIONS", "6"))

# Comma separated list of the meal services the system operates on.
MEAL_SERVICES = [m.strip() for m in env("MEAL_SERVICES", "BREAKFAST,LUNCH,DINNER").split(",") if m.strip()]

# Outbound email. Console backend by default for local development; set
# DJANGO_EMAIL_BACKEND to django.core.mail.backends.smtp.EmailBackend with the
# SMTP variables below for real delivery.
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "mess-forecast@campus.example")

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # the PWA reads it to send writes back
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
    },
}
