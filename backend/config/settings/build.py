"""Image-build settings: only used for `collectstatic` during `docker build`,
where no real secret or database is available."""

from .base import *

SECRET_KEY = "build-time-only-not-used-at-runtime"
DEBUG = False
ALLOWED_HOSTS = ["localhost"]
