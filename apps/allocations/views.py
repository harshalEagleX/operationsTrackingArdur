"""Allocation endpoints."""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action

from apps.allocations.models import BatchAllocation, OrderHistory, OrderRate
from apps.allocations.serializers import (
    AllocationSerializer,
    AllocationStatusSerializer,
    AllocationWriteSerializer,
    OrderHistorySerializer,
    OrderRateSerializer,
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
    lookup_field = "allocation_id"

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
        data = dict(serializer.validated_data)
        
        # Handle uploaded document(s) sent from the frontend
        documents = self.request.FILES.getlist('documents[]')
        if documents:
            # We currently only support saving one document in the BatchAllocation model.
            data['document_file'] = documents[0]
            data['document_name'] = documents[0].name
            
        serializer.instance = self.service.create(data)

    def perform_destroy(self, instance):
        self.service.cancel(instance, reason="Cancelled by supervisor")

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, allocation_id=None):
        """The URL kwarg is ``allocation_id`` (lookup_field above), not
        ``pk`` — every detail action here takes that kwarg name, not the
        DRF default, or the router 500s with a TypeError before the view
        body ever runs."""
        serializer = AllocationStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        allocation = self.service.update_status(self.get_object().pk, **serializer.validated_data)
        return self.ok(AllocationSerializer(allocation).data)

    @action(detail=True, methods=["post"])
    def reassign(self, request, allocation_id=None):
        serializer = ReassignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # ReassignSerializer's wire field is "employee_id" (consistent with
        # AllocationWriteSerializer), but AllocationService.reassign() takes
        # "new_employee_id" — map explicitly rather than **kwargs-splatting
        # a mismatch into a TypeError.
        allocation = self.service.reassign(
            self.get_object(),
            new_employee_id=serializer.validated_data["employee_id"],
            employee_name=serializer.validated_data.get("employee_name", ""),
        )
        return self.ok(AllocationSerializer(allocation).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, allocation_id=None):
        allocation = self.service.cancel(
            self.get_object(), reason=request.data.get("reason", "")
        )
        return self.ok(AllocationSerializer(allocation).data)

    @action(detail=True, methods=["get"])
    def download(self, request, allocation_id=None):
        allocation = self.get_object()
        
        doc_type = request.query_params.get("doc", "document")
        if doc_type == "chain_sheet":
            file_col, name_col = "chain_sheet", "chain_sheet_name"
        elif doc_type == "search_package":
            file_col, name_col = "search_package", "search_package_name"
        elif doc_type == "report":
            file_col, name_col = "report", "report_name"
        else:
            file_col, name_col = "document_file", "document_name"
            
        from django.db import connection
        with connection.cursor() as cursor:
            query = f"SELECT {file_col}, {name_col} FROM ot_batch_allocations WHERE id = %s"
            cursor.execute(query, [allocation.id])
            row = cursor.fetchone()
            
        if not row or not row[0]:
            from core.exceptions import APIError
            raise APIError("No document attached to this order.", status_code=404)
            
        file_bytes = row[0]
        file_name = row[1] or f"order_{allocation.allocation_id}_{doc_type}.bin"
        
        from django.http import HttpResponse
        response = HttpResponse(file_bytes, content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{file_name}"'
        return response

    @action(detail=True, methods=["get"])
    def history(self, request, allocation_id=None):
        allocation = self.get_object()
        rows = OrderHistory.objects.filter(allocation_id=allocation.allocation_id)
        return self.ok(OrderHistorySerializer(rows, many=True).data)

    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request):
        """The caller's open allocations, plus those completed today."""
        queryset = BatchAllocation.objects.for_employee(request.user.emp_id).open_or_completed_today()
        return self.ok(AllocationSerializer(queryset, many=True).data)

    @action(detail=False, methods=["get"], url_path="next_ar_number")
    def next_ar_number(self, request):
        """Return the next auto-generated ar_number."""
        return self.ok({"next_ar_number": BatchAllocation.generate_ar_number()})


class OrderHistoryViewSet(EnvelopeMixin, viewsets.ReadOnlyModelViewSet):
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


class OrderRateViewSet(EnvelopeMixin, viewsets.ReadOnlyModelViewSet):
    """/api/v1/allocations/rates/ — vendor rates and slas."""
    
    serializer_class = OrderRateSerializer
    permission_classes = [IsAuthenticatedEmployee]
    search_fields = ["order_type", "state", "county"]

    def get_queryset(self):
        queryset = OrderRate.objects.all()
        if order_type := self.request.query_params.get("order_type"):
            queryset = queryset.filter(order_type=order_type)
        if state := self.request.query_params.get("state"):
            queryset = queryset.filter(state=state)
        if county := self.request.query_params.get("county"):
            queryset = queryset.filter(county=county)
        return queryset

    @action(detail=False, methods=["get"])
    def order_types(self, request):
        # OrderRate.Meta.ordering is ["order_type", "state", "county"] —
        # without clearing it, Django pulls state/county into the SELECT to
        # satisfy the implicit ORDER BY, and distinct() then dedupes on the
        # (order_type, state, county) tuple instead of order_type alone. The
        # same "Full Search" for two different counties would come back
        # twice. order_by() with no args drops the default ordering.
        types = (
            OrderRate.objects.exclude(order_type__isnull=True).exclude(order_type="")
            .order_by().values_list("order_type", flat=True).distinct()
        )
        return self.ok(
            sorted(types) or ["Current Owner", "Two Owner", "Full Search", "Update Search", "Document Retrieval"]
        )

    @action(detail=False, methods=["get"], url_path="states/(?P<order_type>[^/.]+)")
    def states(self, request, order_type=None):
        states = (
            OrderRate.objects.filter(order_type=order_type)
            .exclude(state__isnull=True).exclude(state="")
            .order_by().values_list("state", flat=True).distinct()
        )
        return self.ok(sorted(states))

    @action(detail=False, methods=["get"], url_path="counties/(?P<order_type>[^/.]+)/(?P<state>[^/.]+)")
    def counties(self, request, order_type=None, state=None):
        counties = (
            OrderRate.objects.filter(order_type=order_type, state=state)
            .exclude(county__isnull=True).exclude(county="")
            .order_by().values_list("county", flat=True).distinct()
        )
        return self.ok(sorted(counties))