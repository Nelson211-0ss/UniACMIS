"""
Production settings for an on-premise campus deployment.

Refuses to boot on an insecure configuration rather than starting up quietly and
exposing student and financial records.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *
from .base import env

DEBUG = False

_INSECURE_KEYS = {"", "changeme", "secret"}
# Prefix match as well as exact value: the shipped development key must never boot
# production, and appending to a key does not make it secret.
if SECRET_KEY in _INSECURE_KEYS or SECRET_KEY.startswith("dev-only-"):
    raise ImproperlyConfigured("SECRET_KEY must be set to a unique value in production.")

if len(SECRET_KEY) < 32:
    # Below 32 bytes an HMAC-SHA256 signing key is weaker than the algorithm it
    # feeds, and every JWT in the system is signed with it.
    raise ImproperlyConfigured("SECRET_KEY must be at least 32 characters long.")

if env.bool("DEBUG", default=False):
    raise ImproperlyConfigured("DEBUG must be False in production.")

if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["*"]:
    raise ImproperlyConfigured("ALLOWED_HOSTS must name the campus hostnames explicitly.")

if ENABLE_DEMO_HOLD_PROVIDER:
    raise ImproperlyConfigured(
        "ENABLE_DEMO_HOLD_PROVIDER is a development stub and must be off in production."
    )

# --------------------------------------------------------- transport security
# NFR-SEC-02: encrypted in transit. Terminated at nginx; Django is told to trust
# that and to refuse to emit cookies over plain HTTP.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Shared campus terminals: an unattended registrar session should not stay open.
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=60 * 60 * 4)

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@localhost")

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
]
