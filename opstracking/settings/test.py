"""Settings for the pytest suite.

Deliberately isolated from dev.py: tests must never touch Redis, send mail, or
depend on a running Celery worker.
"""

from opstracking.settings.base import *  # noqa: F403
from opstracking.settings.base import BASE_DIR, env  # noqa: F401

DEBUG = False
ALLOWED_HOSTS = ["*"]
SECRET_KEY = "test-key-not-secret"

# Legacy tables must be creatable so the test database can be built from
# migrations alone.
LEGACY_TABLES_MANAGED = True

# Locmem instead of Redis — the suite runs with no infrastructure.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

SESSION_ENGINE = "django.contrib.sessions.backends.db"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_RESULT_BACKEND = "cache+memory://"

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Fast hashing — the suite creates a lot of users and bcrypt is deliberately slow.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

PRIVATE_STORAGE_ROOT = BASE_DIR / ".pytest_cache" / "storage"

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

LOGGING["root"]["handlers"] = ["console"]  # noqa: F405
