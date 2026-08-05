"""Master data endpoints.

Read is open to every signed-in employee — every screen needs these lists.
Write is admin-only, which is the fix for "an employee can delete master data".
"""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView

from apps.masters.models import ClientCode, Project, Shift, WorkType
from apps.masters.serializers import (
    ClientCodeSerializer,
    ProjectSerializer,
    ShiftSerializer,
    WorkTypeSerializer,
)
from apps.masters.services import (
    MasterDataService,
    active_client_codes,
    active_projects,
    active_shifts,
    active_work_types,
)
from core.mixins import EnvelopeMixin
from core.permissions import IsAdminOrReadOnly, IsAuthenticatedEmployee


class BaseMasterViewSet(EnvelopeMixin, viewsets.ModelViewSet):
    """CRUD wired to the matching MasterDataService subclass.

    ``?active=true`` filters to live rows; the default returns everything so
    an admin can see and restore what has been deactivated.
    """

    permission_classes = [IsAdminOrReadOnly]

    def get_service(self):
        return MasterDataService.for_model(self.queryset.model)(actor=self.request.user)

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("active") == "true":
            queryset = queryset.active()
        return queryset

    def perform_create(self, serializer):
        serializer.instance = self.get_service().create(dict(serializer.validated_data))

    def perform_update(self, serializer):
        serializer.instance = self.get_service().update(
            serializer.instance, dict(serializer.validated_data)
        )

    def perform_destroy(self, instance):
        self.get_service().deactivate(instance)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        instance = self.get_object()
        self.get_service().update(instance, {"is_active": True})
        return self.ok(self.get_serializer(instance).data)

    @action(detail=True, methods=["delete"], url_path="purge")
    def purge(self, request, pk=None):
        """Hard delete. Refused with 409 if anything references the row."""
        self.get_service().hard_delete(self.get_object())
        return self.ok({"detail": "Deleted."}, status=200)


class WorkTypeViewSet(BaseMasterViewSet):
    queryset = WorkType.objects.all()
    serializer_class = WorkTypeSerializer
    search_fields = ["work_type", "description"]
    ordering_fields = ["work_type", "created_at"]


class ProjectViewSet(BaseMasterViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    search_fields = ["project_name", "project_code", "client_name"]
    ordering_fields = ["project_name", "start_date", "created_at"]


class ClientCodeViewSet(BaseMasterViewSet):
    queryset = ClientCode.objects.all()
    serializer_class = ClientCodeSerializer
    search_fields = ["client_code", "client_name", "project"]
    ordering_fields = ["client_code", "created_at"]


class ShiftViewSet(BaseMasterViewSet):
    queryset = Shift.objects.all()
    serializer_class = ShiftSerializer
    search_fields = ["shift_name"]
    ordering_fields = ["start_time", "shift_name"]


class MasterBundleView(EnvelopeMixin, APIView):
    """GET /api/v1/masters/bundle/

    Every dropdown on a page in one cached request, instead of four.
    """

    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request):
        return self.ok(
            {
                "work_types": active_work_types(),
                "projects": active_projects(),
                "client_codes": active_client_codes(),
                "shifts": active_shifts(),
            }
        )
