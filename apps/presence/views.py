"""Presence endpoints.

Bootstrap only. The page fetches the roster once on load, then applies
``presence.changed`` deltas over the websocket. Never poll these.
"""

from __future__ import annotations

from rest_framework.views import APIView

from apps.presence.serializers import SetStatusSerializer
from apps.presence.services import PresenceService
from core.mixins import EnvelopeMixin
from core.permissions import IsAuthenticatedEmployee


class PresenceRosterView(EnvelopeMixin, APIView):
    """GET /api/v1/presence/ — every employee's current status."""

    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request):
        return self.ok(PresenceService().roster())


class MyPresenceView(EnvelopeMixin, APIView):
    """GET/POST /api/v1/presence/me/"""

    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request):
        return self.ok(PresenceService().get(request.user.emp_id))

    def post(self, request):
        serializer = SetStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        status = PresenceService().set_manual(
            request.user.emp_id,
            serializer.validated_data["status"],
            serializer.validated_data["custom_status"],
        )
        return self.ok({"emp_id": request.user.emp_id, "status": status})


class EmployeePresenceView(EnvelopeMixin, APIView):
    """GET /api/v1/presence/<emp_id>/ — one person's status."""

    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request, emp_id):
        return self.ok(PresenceService().get(emp_id))
