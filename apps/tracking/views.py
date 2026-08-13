"""Work session and target endpoints."""

from __future__ import annotations

from django.db.models import Count, Sum
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView

from apps.tracking.models import Target, WorkSession
from apps.tracking.serializers import (
    EndSessionSerializer,
    StartSessionSerializer,
    TargetSerializer,
    TargetWriteSerializer,
    WorkSessionSerializer,
)
from apps.tracking.services import TargetService, WorkSessionService
from core.mixins import EnvelopeMixin, ServiceMixin
from core.permissions import (
    IsAdminOrSupervisor,
    IsAuthenticatedEmployee,
    IsOwnerOrSupervisor,
)
from core.timezone import today_ist


class WorkSessionViewSet(ServiceMixin, EnvelopeMixin, viewsets.ReadOnlyModelViewSet):
    """/api/v1/tracking/sessions/

    Read-only as a ModelViewSet: every mutation is an explicit, named action,
    because "update a work session" is not one operation — it is start, pause,
    resume or end, each with different rules.
    """

    serializer_class = WorkSessionSerializer
    service_class = WorkSessionService
    permission_classes = [IsOwnerOrSupervisor]
    owner_field = "emp_id"
    ordering = ["-start_time"]

    def get_queryset(self):
        # Row-level scoping. An object permission does not protect a list.
        queryset = WorkSession.objects.visible_to(self.request.user)

        params = self.request.query_params
        if emp_id := params.get("emp_id"):
            queryset = queryset.filter(emp_id=emp_id)
        if project := params.get("project"):
            queryset = queryset.filter(project=project)
        if params.get("open") == "true":
            queryset = queryset.open()
        if params.get("today") == "true":
            queryset = queryset.for_day()
        if date_from := params.get("from"):
            from datetime import datetime
            from core.timezone import start_of_day
            dt = datetime.strptime(date_from, "%Y-%m-%d").date()
            queryset = queryset.filter(start_time__gte=start_of_day(dt))
        if date_to := params.get("to"):
            from datetime import datetime
            from core.timezone import day_bounds
            dt = datetime.strptime(date_to, "%Y-%m-%d").date()
            _, end_dt = day_bounds(dt)
            queryset = queryset.filter(start_time__lt=end_dt)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = StartSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = self.service.start_session(**serializer.validated_data)
        return self.ok(WorkSessionSerializer(session).data, status=201)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        session = self.service.pause_session(int(pk))
        return self.ok(WorkSessionSerializer(session).data)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        session = self.service.resume_session(int(pk))
        return self.ok(WorkSessionSerializer(session).data)

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        serializer = EndSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = self.service.end_session(int(pk), **serializer.validated_data)
        return self.ok(WorkSessionSerializer(session).data)

    def destroy(self, request, *args, **kwargs):
        self.service.delete_session(int(kwargs["pk"]))
        return self.ok({"detail": "Work session removed."})

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        """The caller's own open session, or null. Polled on page load only —
        after that, updates arrive over the websocket."""
        session = WorkSession.objects.filter(emp_id=request.user.emp_id).open().first()
        return self.ok(WorkSessionSerializer(session).data if session else None)

    @action(detail=False, methods=["get"], url_path="active")
    def active(self, request):
        """Everyone currently working — the supervisor floor view."""
        self.check_object_permissions(request, request.user)
        if not request.user.is_supervisor:
            from core.exceptions import PermissionDeniedError

            raise PermissionDeniedError("Only a supervisor can see the floor view.")

        sessions = WorkSession.objects.active_now().order_by("emp_id")
        return self.ok(WorkSessionSerializer(sessions, many=True).data)


class DashboardSummaryView(EnvelopeMixin, APIView):
    """GET /api/v1/tracking/summary/ — one request for the dashboard header."""

    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request):
        emp_id = request.query_params.get("emp_id") or request.user.emp_id

        # Looking at someone else's dashboard is a supervisor action.
        if emp_id != request.user.emp_id and not request.user.is_supervisor:
            from core.exceptions import PermissionDeniedError

            raise PermissionDeniedError("You can only view your own dashboard.")

        today = WorkSession.objects.filter(emp_id=emp_id).for_day().completed()
        totals = today.aggregate(
            sessions=Count("id"), seconds=Sum("total_time")
        )

        open_session = WorkSession.objects.filter(emp_id=emp_id).open().first()
        target = Target.objects.filter(emp_id=emp_id, target_date=today_ist()).first()

        from apps.breaks.models import BreakTime

        on_break = BreakTime.objects.filter(user_id=emp_id, end_time__isnull=True).exists()

        return self.ok(
            {
                "emp_id": emp_id,
                "open_session": WorkSessionSerializer(open_session).data if open_session else None,
                "today_sessions": totals["sessions"] or 0,
                "today_seconds": round(totals["seconds"] or 0, 2),
                "target": TargetSerializer(target).data if target else None,
                "on_break": on_break,
            }
        )


class TargetViewSet(ServiceMixin, EnvelopeMixin, viewsets.ReadOnlyModelViewSet):
    """/api/v1/tracking/targets/ — read for all, write for supervisors."""

    serializer_class = TargetSerializer
    service_class = TargetService
    permission_classes = [IsAuthenticatedEmployee]
    ordering = ["-target_date"]

    def get_queryset(self):
        queryset = Target.objects.visible_to(self.request.user)
        if emp_id := self.request.query_params.get("emp_id"):
            queryset = queryset.filter(emp_id=emp_id)
        if self.request.query_params.get("today") == "true":
            queryset = queryset.for_day()
        return queryset

    def get_permissions(self):
        if self.action == "create":
            return [IsAdminOrSupervisor()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = TargetWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = self.service.set_target(**serializer.validated_data)
        return self.ok(TargetSerializer(target).data, status=201)
