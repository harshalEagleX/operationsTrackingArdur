"""Health and readiness probes.

Deliberately the only unauthenticated endpoints besides login — and both are
on the allowlist in tests/test_url_auth_audit.py, which fails the build if
anything else joins them.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import AllowAnyPublic
from core.timezone import now_ist

logger = logging.getLogger("opstracking.health")


class HealthView(APIView):
    """Liveness. Answers "is this process up?" and nothing more.

    Touches no dependency, so a Redis outage does not make systemd restart a
    perfectly healthy web process.
    """

    permission_classes = [AllowAnyPublic]
    authentication_classes = []

    def get(self, request):
        return Response({"ok": True, "data": {"status": "healthy", "time": now_ist().isoformat()}})


class ReadinessView(APIView):
    """Readiness. Answers "can this process actually serve traffic?"

    Checks the database and the cache, and reports 503 if either is down so a
    deploy script notices before the users do.
    """

    permission_classes = [AllowAnyPublic]
    authentication_classes = []

    def get(self, request):
        checks = {
            "database": self._check_database(),
            "cache": self._check_cache(),
        }
        healthy = all(c["ok"] for c in checks.values())

        return Response(
            {
                "ok": healthy,
                "data": {
                    "status": "ready" if healthy else "degraded",
                    "time": now_ist().isoformat(),
                    "checks": checks,
                    "features": {
                        "chat": settings.FEATURE_CHAT,
                        "presence": settings.FEATURE_PRESENCE,
                        "notifications": settings.FEATURE_NOTIFICATIONS,
                    },
                },
            },
            status=200 if healthy else 503,
        )

    @staticmethod
    def _check_database() -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return {"ok": True}
        except Exception as exc:
            logger.error("readiness: database check failed: %s", exc)
            return {"ok": False, "error": type(exc).__name__}

    @staticmethod
    def _check_cache() -> dict:
        try:
            cache.set("healthcheck", "1", 10)
            return {"ok": cache.get("healthcheck") == "1"}
        except Exception as exc:
            logger.error("readiness: cache check failed: %s", exc)
            return {"ok": False, "error": type(exc).__name__}
