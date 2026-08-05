"""Report endpoints.

Employees may run reports about themselves — the selector forces their own
emp_id onto the filters. Everything cross-employee is supervisor-only.
"""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView

from apps.reports.models import ReportJob
from apps.reports.selectors import REPORT_REGISTRY, dashboard_metrics
from apps.reports.serializers import (
    ReportExportSerializer,
    ReportJobSerializer,
    ReportRunSerializer,
)
from apps.reports.services import ReportService
from core.mixins import EnvelopeMixin, ServiceMixin
from core.permissions import IsAdminOrSupervisor, IsAuthenticatedEmployee
from core.throttling import ReportExportThrottle


class ReportCatalogueView(EnvelopeMixin, APIView):
    """GET /api/v1/reports/ — what reports exist and what columns they have."""

    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request):
        from apps.reports.selectors import ReportFilters

        return self.ok(
            [
                {
                    "key": key,
                    "label": key.replace("_", " ").title(),
                    "columns": [
                        {"key": column, "label": label}
                        for column, label in selector_class(ReportFilters()).columns
                    ],
                }
                for key, selector_class in sorted(REPORT_REGISTRY.items())
            ]
        )


class ReportRunView(ServiceMixin, EnvelopeMixin, APIView):
    """POST /api/v1/reports/run/ — execute a report and return its rows."""

    permission_classes = [IsAuthenticatedEmployee]
    service_class = ReportService

    def post(self, request):
        serializer = ReportRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        params = dict(serializer.validated_data)
        report_key = params.pop("report_key")

        result = self.service.run(report_key, params)
        return self.ok(result["rows"], meta={
            "report_key": result["report_key"],
            "columns": result["columns"],
            "row_count": result["row_count"],
            "truncated": result["truncated"],
        })


class ReportExportView(ServiceMixin, EnvelopeMixin, APIView):
    """POST /api/v1/reports/export/ — queue an export, return 202.

    The browser gets an immediate response and a job id. The file arrives as
    a notification with a download link when the worker is done.
    """

    permission_classes = [IsAuthenticatedEmployee]
    service_class = ReportService
    throttle_classes = [ReportExportThrottle]
    throttle_scope = "report_export"

    def post(self, request):
        serializer = ReportExportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        params = dict(serializer.validated_data)
        report_key = params.pop("report_key")
        export_format = params.pop("export_format")

        job = self.service.queue_export(report_key, params, export_format)
        return self.ok(ReportJobSerializer(job).data, status=202)


class ReportJobViewSet(ServiceMixin, EnvelopeMixin, viewsets.ReadOnlyModelViewSet):
    """/api/v1/reports/jobs/ — export job status."""

    serializer_class = ReportJobSerializer
    service_class = ReportService
    permission_classes = [IsAuthenticatedEmployee]
    ordering = ["-id"]

    def get_queryset(self):
        queryset = ReportJob.objects.select_related("file")
        if not self.request.user.is_supervisor:
            queryset = queryset.filter(requested_by=self.request.user.emp_id)
        if status_value := self.request.query_params.get("status"):
            queryset = queryset.filter(status=status_value)
        return queryset

    @action(detail=False, methods=["get"], url_path="pending")
    def pending(self, request):
        """Jobs still running — the client polls this only while a spinner is
        on screen, then stops. Completion also arrives as a notification."""
        queryset = self.get_queryset().filter(status__in=("queued", "running"))
        return self.ok(ReportJobSerializer(queryset, many=True).data)


class DashboardMetricsView(EnvelopeMixin, APIView):
    """GET /api/v1/reports/metrics/ — the supervisor dashboard headline row."""

    permission_classes = [IsAdminOrSupervisor]

    def get(self, request):
        return self.ok(dashboard_metrics(request.user))
