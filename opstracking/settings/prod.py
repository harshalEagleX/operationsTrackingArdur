"""Production settings.

DEBUG is assigned False literally — not read from the environment — so that a
stray ``DEBUG=True`` in a deployed .env cannot switch it back on.
"""

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from opstracking.settings.base import *  # noqa: F403
from opstracking.settings.base import LOGGING, env  # noqa: F401

DEBUG = False

SECRET_KEY = env("SECRET_KEY")  # no default: fail loudly rather than run insecure
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# Legacy tables already exist and hold live data. Django must never issue DDL
# against them. Adopt them once with: manage.py migrate --fake-initial
LEGACY_TABLES_MANAGED = env.bool("LEGACY_TABLES_MANAGED", default=False)

# ───────────────────────── transport security ────────────────
# Apache terminates TLS and sets X-Forwarded-Proto.

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False  # the JS fetch wrapper reads it for X-CSRFToken

# ───────────────────────── static files ──────────────────────
# Hashed filenames let Apache cache /static/ for a year and still ship changes.

STORAGES = {
    "default": {"BACKEND": "apps.files.storage.PrivateStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ───────────────────────── observability ─────────────────────

SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
    )

LOGGING["handlers"]["file"]["filename"] = env(  # noqa: F405
    "DJANGO_LOG_FILE", default="/home/opsuser/logs/django.log"
)
