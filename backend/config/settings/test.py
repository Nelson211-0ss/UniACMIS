"""Test settings. Runs against real PostgreSQL — the audit hash chain uses
advisory locks and several invariants rely on real constraint enforcement, so
SQLite would test something other than what we ship."""

from .base import *
from .base import env  # noqa: F401

DEBUG = False

# Fast hashing: the Argon2 cost that protects real accounts makes tests crawl.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# The stub hold provider is what FR-ENR-03's integration test exercises.
ENABLE_DEMO_HOLD_PROVIDER = True

# Throttling would make deterministic tests flaky; the throttle behaviour itself
# is asserted explicitly where it matters.
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []

LOGGING["root"]["level"] = "WARNING"
