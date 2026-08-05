"""Application settings endpoints."""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action

from apps.settings_app.models import AppSetting
from apps.settings_app.serializers import AppSettingSerializer, SettingWriteSerializer
from apps.settings_app.services import SettingsService
from core.mixins import EnvelopeMixin, ServiceMixin
from core.permissions import IsAdminOrReadOnly


class AppSettingViewSet(ServiceMixin, EnvelopeMixin, viewsets.ReadOnlyModelViewSet):
    """/api/v1/settings/

    Readable by any signed-in employee (the frontend needs the branding and
    behaviour flags); writable only by an admin.
    """

    queryset = AppSetting.objects.all()
    serializer_class = AppSettingSerializer
    service_class = SettingsService
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = "key"
    lookup_value_regex = "[^/]+"

    def get_queryset(self):
        queryset = super().get_queryset()
        if category := self.request.query_params.get("category"):
            queryset = queryset.filter(category=category)
        return queryset

    @action(detail=False, methods=["get"], url_path="map")
    def as_map(self, request):
        """A flat key → value object, for the frontend to hold in its store."""
        return self.ok(SettingsService.all_settings())

    @action(detail=False, methods=["post"], url_path="set")
    def set_value(self, request):
        serializer = SettingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        setting = self.service.set(
            serializer.validated_data["key"], serializer.validated_data["value"]
        )
        return self.ok(AppSettingSerializer(setting).data)
