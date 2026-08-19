"""
Base settings shared by every environment.

Anything an institution can change without a deployment belongs in the database
(see apps.academics), not here — NFR-MAINT-03. What lives here is infrastructure.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# Compose passes the environment in directly; reading the file matters when
# running manage.py outside a container.
_env_file = BASE_DIR.parent / ".env"
if _env_file.exists():
    environ.Env.read_env(_env_file)

# --------------------------------------------------------------------- security

# The `dev-only-` prefix is what config/settings/prod.py refuses to boot with, and
# the length keeps PyJWT from warning about a signing key weaker than HMAC-SHA256.
SECRET_KEY = env("SECRET_KEY", default="dev-only-insecure-key-change-me-before-any-real-deployment")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Argon2 first: NFR-SEC-04 requires salted one-way hashing, and student and
# financial records make this a worthwhile upgrade over the PBKDF2 default.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ------------------------------------------------------------------------- apps

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
]

# Order matters: lower layers first, so AppConfig.ready() port registration in a
# domain app always finds core's registry already importable.
LOCAL_APPS = [
    "apps.core",
    "apps.audit",
    "apps.accounts",
    "apps.academics",
    "apps.curriculum",
    "apps.registry",
    "apps.admissions",
    "apps.enrollment",
    "apps.timetabling",
    "apps.attendance",
    "apps.examinations",
    "apps.hr",
    "apps.library",
    "apps.hostel",
    "apps.finance",
    "apps.documents",
    "apps.communications",
    "apps.alumni",
    "apps.reporting",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ------------------------------------------------------------------- middleware

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Early, so even a failure in a later middleware still carries a request id.
    "apps.core.middleware.RequestIDMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # After authentication: the audit trail needs to know who is acting.
    "apps.core.middleware.AuditActorMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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
            ],
        },
    },
]

# --------------------------------------------------------------------- database

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgres://uniacmis:uniacmis@localhost:5432/uniacmis",
    ),
}
# Power cuts are routine here, so connections are validated rather than blindly
# reused after an outage (NFR-AVAIL-02).
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------- i18n / localisation

LANGUAGE_CODE = env("LANGUAGE_CODE", default="en-us")
TIME_ZONE = env("TIME_ZONE", default="Africa/Juba")
USE_I18N = True
USE_TZ = True  # storage is always UTC; TIME_ZONE is for presentation
LOCALE_PATHS = [BASE_DIR / "locale"]

LANGUAGES = [
    ("en", "English"),
    ("ar", "Arabic"),  # NFR-USE-01: public-facing notices may need Arabic
]

# ------------------------------------------------------------ static and media

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

MAX_UPLOAD_SIZE_MB = env.int("MAX_UPLOAD_SIZE_MB", default=5)

FILE_STORAGE_BACKEND = env("FILE_STORAGE_BACKEND", default="local")
if FILE_STORAGE_BACKEND == "minio":
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "endpoint_url": env("MINIO_ENDPOINT", default="http://minio:9000"),
                "access_key": env("MINIO_ACCESS_KEY", default=""),
                "secret_key": env("MINIO_SECRET_KEY", default=""),
                "bucket_name": env("MINIO_BUCKET", default="uniacmis"),
            },
        },
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }

# ------------------------------------------------------------------------- DRF

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Deny by default. An endpoint opens itself deliberately, never by omission.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "sync": "120/min",
        "verification": "20/min",  # public document verification, Phase 6
    },
    "DEFAULT_VERSIONING_CLASS": None,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "UniACMIS API",
    "DESCRIPTION": (
        "University Academic Management Information System — South Sudan.\n\n"
        "Offline-capable modules submit queued writes to /sync/batch, which is "
        "idempotent on client_op_id."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("ACCESS_TOKEN_LIFETIME_MINUTES", default=30)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("REFRESH_TOKEN_LIFETIME_DAYS", default=7)),
    # Campus machines are shared, so a leaked refresh token must be revocable.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"])
CORS_ALLOW_CREDENTIALS = True

# ------------------------------------------------------------- Celery / Redis

CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True  # a worker killed by a power cut must not lose the task
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# ------------------------------------------------------------- UniACMIS domain

# Currency: SSP primary, USD secondary (SRS §2.5). Amounts are always stored
# with their currency; cross-currency values also record the FX rate used.
DEFAULT_CURRENCY = env("DEFAULT_CURRENCY", default="SSP")
SECONDARY_CURRENCY = env("SECONDARY_CURRENCY", default="USD")

# Pluggable providers (ARCHITECTURE §8). Business logic never imports an SDK.
NOTIFICATION_PROVIDER = env(
    "NOTIFICATION_PROVIDER",
    default="apps.core.providers.notifications.ConsoleNotificationProvider",
)
PAYMENT_PROVIDER = env(
    "PAYMENT_PROVIDER",
    default="apps.core.providers.payments.MockPaymentProvider",
)

LOGIN_MAX_FAILED_ATTEMPTS = env.int("LOGIN_MAX_FAILED_ATTEMPTS", default=5)
LOGIN_LOCKOUT_MINUTES = env.int("LOGIN_LOCKOUT_MINUTES", default=15)

# NFR-SEC-03: access and modification logs for grade and financial records are
# retained for at least five years.
AUDIT_RETENTION_YEARS = env.int("AUDIT_RETENTION_YEARS", default=5)

# Stub fee-balance hold provider, so FR-ENR-03 is demonstrable before the
# finance module exists. Must stay off in production.
ENABLE_DEMO_HOLD_PROVIDER = env.bool("ENABLE_DEMO_HOLD_PROVIDER", default=False)

# -------------------------------------------------------------------- logging

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "apps": {
            "level": env("LOG_LEVEL", default="INFO"),
            "handlers": ["console"],
            "propagate": False,
        },
    },
}
