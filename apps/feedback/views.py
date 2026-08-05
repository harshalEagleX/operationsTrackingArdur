"""Feedback endpoints.

Two layers of access control, both needed:
  * ``get_queryset`` scopes the list — an object permission never runs on it.
  * ``IsOwnerOrSupervisor`` guards detail, update and delete.
"""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action

from apps.feedback.models import Feedback
from apps.feedback.serializers import (
    AcknowledgeSerializer,
    FeedbackSerializer,
    FeedbackWriteSerializer,
)
from apps.feedback.services import FeedbackService
from core.mixins import EnvelopeMixin, ServiceMixin
from core.permissions import IsAdminOrSupervisor, IsAuthenticatedEmployee


class FeedbackViewSet(ServiceMixin, EnvelopeMixin, viewsets.ModelViewSet):
    """/api/v1/feedback/"""

    serializer_class = FeedbackSerializer
    service_class = FeedbackService
    permission_classes = [IsAuthenticatedEmployee]
    search_fields = ["subject", "description", "order_batch_id", "emp_id"]
    ordering_fields = ["created_at", "severity"]
    ordering = ["-created_at"]

    def get_permissions(self):
        if self.action in ("create", "destroy"):
            return [IsAdminOrSupervisor()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return FeedbackWriteSerializer
        return FeedbackSerializer

    def get_queryset(self):
        queryset = (
            Feedback.objects.visible_to(self.request.user)
            .prefetch_related("images__file")
        )

        params = self.request.query_params
        if emp_id := params.get("emp_id"):
            queryset = queryset.filter(emp_id=emp_id)
        if feedback_type := params.get("type"):
            queryset = queryset.filter(feedback_type=feedback_type)
        if severity := params.get("severity"):
            queryset = queryset.filter(severity=severity)
        if params.get("unacknowledged") == "true":
            queryset = queryset.unacknowledged()
        if date_from := params.get("from"):
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to := params.get("to"):
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset

    def get_object(self):
        """Re-assert the read rule on detail.

        get_queryset already scopes it, but this is the line that makes the
        intent explicit and survives someone later "optimising" the queryset.
        """
        obj = super().get_object()
        service = self.service
        if not service.can_read(obj):
            from core.exceptions import PermissionDeniedError

            raise PermissionDeniedError("That feedback is about someone else.")
        return obj

    def create(self, request, *args, **kwargs):
        serializer = FeedbackWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = dict(serializer.validated_data)
        file_ids = data.pop("file_ids", [])
        feedback = self.service.create(data, file_ids=file_ids)
        return self.ok(FeedbackSerializer(feedback).data, status=201)

    def perform_update(self, serializer):
        data = dict(serializer.validated_data)
        data.pop("file_ids", None)
        serializer.instance = self.service.update(serializer.instance, data)

    def perform_destroy(self, instance):
        self.service.delete(instance)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        serializer = AcknowledgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feedback = self.service.acknowledge(int(pk), serializer.validated_data["response"])
        return self.ok(FeedbackSerializer(feedback).data)

    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request):
        """Feedback about the caller — the employee's own feedback tab."""
        queryset = (
            Feedback.objects.filter(emp_id=request.user.emp_id)
            .prefetch_related("images__file")
            .order_by("-created_at")
        )
        page = self.paginate_queryset(queryset)
        serializer = FeedbackSerializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return self.ok(serializer.data)
