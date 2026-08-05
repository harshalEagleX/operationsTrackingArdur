"""Root URLConf.

Three trees, kept deliberately separate:

    /api/v1/...   JSON, DRF, session-authenticated  → opstracking/api_urls.py
    /...          server-rendered Jinja2 screens    → pages/urls.py
    /admin/       Django admin (staff only)
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from core.views import HealthView, ReadinessView

urlpatterns = [
    # Probed by systemd/deploy scripts and the load balancer. Unauthenticated
    # by design — listed on the allowlist in tests/test_url_auth_audit.py.
    path("health/", HealthView.as_view(), name="health"),
    path("ready/", ReadinessView.as_view(), name="ready"),
    path("admin/", admin.site.urls),
    path("api/v1/", include(("opstracking.api_urls", "api"), namespace="api")),
    path("", include("pages.urls")),
]

if settings.DEBUG:
    urlpatterns += [path("api-auth/", include("rest_framework.urls"))]
