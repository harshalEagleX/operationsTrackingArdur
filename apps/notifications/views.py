"""Notification endpoints.

Bootstrap and management only. New notifications arrive over the websocket —
the bell badge is never polled.
"""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView

from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.registry import configurable_types
from apps.notifications.serializers import (
    MarkReadSerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer,
    PreferenceWriteSerializer,
)
from apps.notifications.services import NotificationService
from core.mixins import EnvelopeMixin, ServiceMixin
from core.pagination import KeysetPagination
from core.permissions import IsAuthenticatedEmployee


class NotificationViewSet(ServiceMixin, EnvelopeMixin, viewsets.ReadOnlyModelViewSet):
    """/api/v1/notifications/

    Keyset paginated: an inbox grows forever, and OFFSET on page 40 makes the
    database walk 2,000 rows to return 50.
    """

    serializer_class = NotificationSerializer
    service_class = NotificationService
    permission_classes = [IsAuthenticatedEmployee]
    pagination_class = None  # keyset instead — see get_queryset

    def get_queryset(self):
        queryset = Notification.objects.filter(
            recipient_emp_id=self.request.user.emp_id
        ).order_by("-id")

        if self.request.query_params.get("unread") == "true":
            queryset = queryset.filter(read_at__isnull=True)
        if notif_type := self.request.query_params.get("type"):
            queryset = queryset.filter(notif_type=notif_type)

        return KeysetPagination.apply(queryset, self.request)

    def list(self, request, *args, **kwargs):
        items = list(self.get_queryset())
        serialized = NotificationSerializer(items, many=True).data
        payload = KeysetPagination.envelope(items, serialized)
        payload["meta"]["unread_count"] = NotificationService.unread_count(request.user.emp_id)
        from rest_framework.response import Response

        return Response(payload)

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        """The bell badge on page load. After that, deltas arrive by socket."""
        return self.ok({"unread_count": NotificationService.unread_count(request.user.emp_id)})

    @action(detail=False, methods=["post"], url_path="read")
    def mark_read(self, request):
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        count = self.service.mark_read(
            request.user.emp_id, serializer.validated_data.get("ids") or None
        )
        return self.ok({"marked": count})


class NotificationPreferenceView(EnvelopeMixin, APIView):
    """GET/POST /api/v1/notifications/preferences/

    The GET merges stored overrides onto the registry defaults, so the screen
    always shows every configurable type — including ones added since the user
    last visited.
    """

    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request):
        stored = {
            p.notif_type: p
            for p in NotificationPreference.objects.filter(emp_id=request.user.emp_id)
        }

        return self.ok(
            [
                {
                    "notif_type": spec.key,
                    "description": spec.description,
                    "priority": spec.priority,
                    "in_app": stored[spec.key].in_app if spec.key in stored
                    else spec.default_in_app,
                    "email": stored[spec.key].email if spec.key in stored
                    else spec.default_email,
                }
                for spec in configurable_types()
            ]
        )

    def post(self, request):
        serializer = PreferenceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        preference = NotificationService(actor=request.user).set_preference(
            request.user.emp_id,
            serializer.validated_data["notif_type"],
            in_app=serializer.validated_data["in_app"],
            email=serializer.validated_data["email"],
        )
        return self.ok(NotificationPreferenceSerializer(preference).data)
