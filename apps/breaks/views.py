"""Break endpoints."""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView

from apps.breaks.constants import BREAK_ALLOWANCES, is_repeatable
from apps.breaks.models import BreakTime
from apps.breaks.serializers import (
    BreakSerializer,
    EndBreakSerializer,
    StartBreakSerializer,
)
from apps.breaks.services import BreakService
from core.mixins import EnvelopeMixin, ServiceMixin
from core.permissions import IsAdminOrSupervisor, IsAuthenticatedEmployee, IsOwnerOrSupervisor


class BreakViewSet(ServiceMixin, EnvelopeMixin, viewsets.ReadOnlyModelViewSet):
    """/api/v1/breaks/"""

    serializer_class = BreakSerializer
    service_class = BreakService
    permission_classes = [IsOwnerOrSupervisor]
    owner_field = "user_id"
    ordering = ["-start_time"]

    def get_queryset(self):
        queryset = BreakTime.objects.visible_to(self.request.user)

        params = self.request.query_params
        if emp_id := params.get("emp_id"):
            queryset = queryset.filter(user_id=emp_id)
        if params.get("open") == "true":
            queryset = queryset.open()
        if params.get("today") == "true":
            queryset = queryset.for_day()
        if date_from := params.get("from"):
            queryset = queryset.filter(start_time__date__gte=date_from)
        if date_to := params.get("to"):
            queryset = queryset.filter(start_time__date__lte=date_to)
        return queryset

    def create(self, request, *args, **kwargs):
        """POST /api/v1/breaks/ — start a break."""
        serializer = StartBreakSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        brk = self.service.start_break(serializer.validated_data["break_type"])
        return self.ok(BreakSerializer(brk).data, status=201)

    @action(detail=False, methods=["post"])
    def end(self, request):
        """POST /api/v1/breaks/end/ — end your open break."""
        serializer = EndBreakSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        brk = self.service.end_break(serializer.validated_data.get("break_id"))
        return self.ok(BreakSerializer(brk).data)

    @action(detail=True, methods=["post"], url_path="force-end",
            permission_classes=[IsAdminOrSupervisor])
    def force_end(self, request, pk=None):
        """Supervisor closes a break someone forgot to end."""
        brk = self.service.force_end_break(int(pk))
        return self.ok(BreakSerializer(brk).data)

    @action(detail=False, methods=["get"])
    def current(self, request):
        """The caller's open break, or null."""
        brk = self.service.current_break()
        return self.ok(BreakSerializer(brk).data if brk else None)

    @action(detail=False, methods=["get"], url_path="active",
            permission_classes=[IsAdminOrSupervisor])
    def active(self, request):
        """Everyone currently on a break — the supervisor floor view."""
        breaks = BreakTime.objects.open().order_by("start_time")
        return self.ok(BreakSerializer(breaks, many=True).data)


class BreakTypeListView(EnvelopeMixin, APIView):
    """GET /api/v1/breaks/types/

    Returns the allowances so the UI can render a countdown, plus whether the
    caller has already used each one today. The client displays these; it
    never sends them back.
    """

    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request):
        taken = set(
            BreakTime.objects.filter(user_id=request.user.emp_id)
            .for_day()
            .values_list("break_type", flat=True)
        )

        return self.ok(
            [
                {
                    "break_type": name,
                    "allotted_seconds": seconds,
                    "allotted_minutes": seconds // 60,
                    "repeatable": is_repeatable(name),
                    "taken_today": name in taken and not is_repeatable(name),
                }
                for name, seconds in BREAK_ALLOWANCES.items()
            ]
        )
