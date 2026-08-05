"""Allocation endpoints."""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action

from apps.allocations.models import BatchAllocation, OrderHistory
from apps.allocations.serializers import (
    AllocationSerializer,
    AllocationStatusSerializer,
    AllocationWriteSerializer,
    OrderHistorySerializer,
    ReassignSerializer,
)
from apps.allocations.services import AllocationService
from core.mixins import EnvelopeMixin, ServiceMixin
from core.permissions import IsAdminOrSupervisor, IsAuthenticatedEmployee


class AllocationViewSet(ServiceMixin, EnvelopeMixin, viewsets.ModelViewSet):
    """/api/v1/allocations/

    Employees see and progress their own work. Creating, reassigning and
    cancelling are supervisor actions.
    """

    serializer_class = AllocationSerializer
    service_class = AllocationService
    permission_classes = [IsAuthenticatedEmployee]
    search_fields = ["allocation_id", "order_id", "batch", "employee_id", "project"]
    ordering_fields = ["allocated_at", "due_at", "priority", "status"]
    ordering = ["-allocated_at"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy",
                           "reassign", "cancel"):
            return [IsAdminOrSupervisor()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return AllocationWriteSerializer
        return AllocationSerializer

    def get_queryset(self):
        queryset = BatchAllocation.objects.visible_to(self.request.user)

        params = self.request.query_params
        if emp_id := params.get("emp_id"):
            queryset = queryset.filter(employee_id=emp_id)
        if status_value := params.get("status"):
            queryset = queryset.filter(status=status_value)
        if params.get("open") == "true":
            queryset = queryset.open()
        if params.get("overdue") == "true":
            queryset = queryset.overdue()
        if project := params.get("project"):
            queryset = queryset.filter(project=project)
        return queryset

    def perform_create(self, serializer):
        serializer.instance = self.service.create(dict(serializer.validated_data))

    def perform_destroy(self, instance):
        self.service.cancel(instance, reason="Cancelled by supervisor")

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        serializer = AllocationStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        allocation = self.service.update_status(int(pk), **serializer.validated_data)
        return self.ok(AllocationSerializer(allocation).data)

    @action(detail=True, methods=["post"])
    def reassign(self, request, pk=None):
        serializer = ReassignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        allocation = self.service.reassign(self.get_object(), **serializer.validated_data)
        return self.ok(AllocationSerializer(allocation).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        allocation = self.service.cancel(
            self.get_object(), reason=request.data.get("reason", "")
        )
        return self.ok(AllocationSerializer(allocation).data)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        allocation = self.get_object()
        rows = OrderHistory.objects.filter(allocation_id=allocation.allocation_id)
        return self.ok(OrderHistorySerializer(rows, many=True).data)

    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request):
        """The caller's open allocations — the 'my tasks' panel."""
        queryset = BatchAllocation.objects.for_employee(request.user.emp_id).open()
        return self.ok(AllocationSerializer(queryset, many=True).data)


class OrderHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """/api/v1/allocations/history/ — the audit trail, supervisors only."""

    serializer_class = OrderHistorySerializer
    permission_classes = [IsAdminOrSupervisor]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = OrderHistory.objects.all()
        if allocation_id := self.request.query_params.get("allocation_id"):
            queryset = queryset.filter(allocation_id=allocation_id)
        if emp_id := self.request.query_params.get("emp_id"):
            queryset = queryset.filter(employee_id=emp_id)
        return queryset
