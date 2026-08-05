"""The /api/v1/ surface.

Each app owns its own routes. This module only mounts them, so adding an
endpoint never means editing a shared 400-line router file.
"""

from django.conf import settings
from django.urls import include, path

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    path("masters/", include("apps.masters.urls")),
    path("tracking/", include("apps.tracking.urls")),
    path("breaks/", include("apps.breaks.urls")),
    path("allocations/", include("apps.allocations.urls")),
    path("feedback/", include("apps.feedback.urls")),
    path("reports/", include("apps.reports.urls")),
    path("settings/", include("apps.settings_app.urls")),
    path("files/", include("apps.files.urls")),
    path("realtime/", include("apps.realtime.urls")),
]

if settings.FEATURE_PRESENCE:
    urlpatterns += [path("presence/", include("apps.presence.urls"))]

if settings.FEATURE_NOTIFICATIONS:
    urlpatterns += [path("notifications/", include("apps.notifications.urls"))]

# ── Chat is scaffolded but not implemented ────────────────────
# When apps.chat is built, add it to INSTALLED_APPS and uncomment:
#
# if settings.FEATURE_CHAT:
#     urlpatterns += [path("chat/", include("apps.chat.urls"))]
