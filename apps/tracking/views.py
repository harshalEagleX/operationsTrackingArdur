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

    @action(detail=True, methods=["post"], url_path="indexing-submit")
    def indexing_submit(self, request, pk=None):
        units = request.data.get("units")
        if not units:
            return self.error("Number of units is required.", status=400)
        try:
            units = int(units)
        except ValueError:
            return self.error("Units must be an integer.", status=400)
            
        result = self.service.indexing_submit(int(pk), units)
        return self.ok({
            "ended_session": WorkSessionSerializer(result["ended_session"]).data,
            "new_session": WorkSessionSerializer(result["new_session"]).data,
            "units_submitted": result["units_submitted"]
        })

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
        from apps.accounts.models import LoginHistory
        from core.timezone import now_ist

        today_breaks = BreakTime.objects.filter(user_id=emp_id, start_time__date=today_ist())
        on_break = today_breaks.filter(end_time__isnull=True).exists()

        break_seconds = 0
        for b in today_breaks:
            end_val = b.end_time or now_ist()
            break_seconds += (end_val - b.start_time).total_seconds()
            
        login_record = LoginHistory.objects.filter(emp_id=emp_id, date=today_ist()).order_by('login_time').first()
        login_time = login_record.login_time if login_record else None
        logout_time = login_record.logout_time if login_record else None
        
        gross_seconds = 0
        if login_time:
            end_val = logout_time or now_ist()
            gross_seconds = (end_val - login_time).total_seconds()
            
        net_seconds = max(0, gross_seconds - break_seconds)

        return self.ok(
            {
                "emp_id": emp_id,
                "open_session": WorkSessionSerializer(open_session).data if open_session else None,
                "today_sessions": totals["sessions"] or 0,
                "today_seconds": round(totals["seconds"] or 0, 2),
                "target": TargetSerializer(target).data if target else None,
                "on_break": on_break,
                "attendance": {
                    "login_time": login_time.isoformat() if login_time else None,
                    "logout_time": logout_time.isoformat() if logout_time else None,
                    "break_seconds": round(break_seconds),
                    "net_seconds": round(net_seconds),
                }
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
        target = self.service_class.assign_target(
            serializer.validated_data, request.user.emp_id
        )
        return self.created(TargetSerializer(target).data)


class MonthlyAttendanceView(EnvelopeMixin, APIView):
    """GET /api/v1/tracking/attendance-history/"""
    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request):
        emp_id = request.query_params.get("emp_id") or request.user.emp_id
        if emp_id != request.user.emp_id and not request.user.is_supervisor:
            from core.exceptions import PermissionDeniedError
            raise PermissionDeniedError("You can only view your own attendance.")

        from apps.breaks.models import BreakTime
        from apps.accounts.models import LoginHistory
        from core.timezone import now_ist
        
        now = now_ist()
        start_date = now.replace(day=1).date()
        
        logins = LoginHistory.objects.filter(emp_id=emp_id, date__gte=start_date).order_by('date', 'login_time')
        breaks = BreakTime.objects.filter(user_id=emp_id, start_time__date__gte=start_date)
        
        daily_data = {}
        for b in breaks:
            b_date = b.start_time.date()
            if b_date not in daily_data:
                daily_data[b_date] = {'breaks': 0, 'login': None, 'logout': None}
            end_val = b.end_time or now
            daily_data[b_date]['breaks'] += (end_val - b.start_time).total_seconds()
            
        for l in logins:
            l_date = l.date
            if l_date not in daily_data:
                daily_data[l_date] = {'breaks': 0, 'login': None, 'logout': None}
            
            if not daily_data[l_date]['login']:
                daily_data[l_date]['login'] = l.login_time
            daily_data[l_date]['logout'] = l.logout_time
            
        results = []
        for d in sorted(daily_data.keys(), reverse=True):
            data = daily_data[d]
            login_time = data['login']
            logout_time = data['logout']
            break_secs = data['breaks']
            
            gross_secs = 0
            if login_time:
                end_val = logout_time or (now if d == now.date() else login_time)
                gross_secs = (end_val - login_time).total_seconds()
            net_secs = max(0, gross_secs - break_secs)
            
            results.append({
                "date": d.isoformat(),
                "login_time": login_time.isoformat() if login_time else None,
                "logout_time": logout_time.isoformat() if logout_time else None,
                "break_seconds": round(break_secs),
                "net_seconds": round(net_secs)
            })
            
        return self.ok(results)
