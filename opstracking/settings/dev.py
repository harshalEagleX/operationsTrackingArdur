"""Local development settings. Never deploy this module."""

from opstracking.settings.base import *  # noqa: F403
from opstracking.settings.base import BASE_DIR, INSTALLED_APPS, env  # noqa: F401

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Cookies over plain HTTP — localhost has no certificate.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:8000", "http://127.0.0.1:8000", "https://*.trycloudflare.com"],
)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Run Celery tasks inline. No worker needed to click through the app; start a
# real worker with `make worker` when you want to exercise the queue itself.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)
CELERY_TASK_EAGER_PROPAGATES = True

# In development on Windows, use InMemory channel layer & cache for zero friction
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

try:
    import django_extensions  # noqa: F401

    INSTALLED_APPS = [*INSTALLED_APPS, "django_extensions"]
except ImportError:
    pass

