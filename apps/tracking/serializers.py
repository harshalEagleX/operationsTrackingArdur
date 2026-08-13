"""Work session and target serializers.

Note what the write serializers deliberately do *not* accept: ``start_time``,
``end_time``, ``total_time``, ``average_time``. Those are server-computed. A
client that sends them is ignored rather than trusted.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.tracking.models import SessionState, Target, WorkSession
from core.validators import validate_emp_id

class WorkSessionSerializer(serializers.ModelSerializer):
    """Read shape."""

    state = serializers.SerializerMethodField()
    live_elapsed_seconds = serializers.FloatField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    client_name = serializers.SerializerMethodField()
    order_type = serializers.SerializerMethodField()
    project_name = serializers.SerializerMethodField()
    work_location = serializers.SerializerMethodField()

    def get_work_location(self, obj):
        from apps.accounts.models import Employee
        employee = Employee.objects.filter(employee_id=obj.emp_id).first()
        return employee.department if employee else ""

    def get_project_name(self, obj):
        from apps.masters.models import Project
        project = Project.objects.filter(project_id=obj.project).first()
        return project.project_name if project else obj.project

    def get_order_type(self, obj):
        from apps.allocations.models import BatchAllocation
        if obj.allocation_id:
            alloc = BatchAllocation.objects.filter(allocation_id=obj.allocation_id).first()
            if alloc:
                return alloc.order_id
        return ""

    def get_client_name(self, obj):
        from apps.masters.models import ClientCode
        client = ClientCode.objects.filter(client_code=obj.client_code).first()
        return client.client_name if client else obj.client_code

    class Meta:
        model = WorkSession
        fields = [
            "id", "emp_id", "name", "project", "project_name", "client_code", "client_name", "work_type", "batch",
            "order_type",
            "start_time", "end_time", "total_time",
            "is_paused", "paused_at", "paused_elapsed", "allocation_id",
            "is_started", "state", "is_open", "live_elapsed_seconds",
            "review", "work_location",
        ]
        read_only_fields = fields

    def get_state(self, obj) -> str:
        return SessionState(int(obj.is_started)).label.lower()


class StartSessionSerializer(serializers.Serializer):
    """Input for POST /tracking/sessions/."""

    project = serializers.CharField(max_length=150)
    work_type = serializers.CharField(max_length=100)
    client_code = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    batch = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    allocation_id = serializers.CharField(
        max_length=50, required=False, allow_blank=True, allow_null=True, default=None
    )


class EndSessionSerializer(serializers.Serializer):
    """Input for POST /tracking/sessions/{id}/end/.

    There is no ``end_time`` field. That is the point.
    """

    review = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    chain_sheet = serializers.FileField(required=False, allow_null=True)
    search_package = serializers.FileField(required=False, allow_null=True)
    report = serializers.FileField(required=False, allow_null=True)
    employee_comments = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class TargetSerializer(serializers.ModelSerializer):
    completion_percent = serializers.FloatField(read_only=True)
    is_met = serializers.BooleanField(read_only=True)

    class Meta:
        model = Target
        fields = [
            "id", "emp_id", "project", "work_type", "target_date",
            "target_units", "achieved_units", "completion_percent", "is_met",
            "created_by", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "achieved_units", "completion_percent", "is_met",
            "created_by", "created_at", "updated_at",
        ]


class TargetWriteSerializer(serializers.Serializer):
    emp_id = serializers.CharField(max_length=20, validators=[validate_emp_id])
    target_date = serializers.DateField()
    target_units = serializers.IntegerField(min_value=0, max_value=100_000)
    project = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    work_type = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class DashboardSummarySerializer(serializers.Serializer):
    """What the user dashboard shows above the fold."""

    open_session = WorkSessionSerializer(allow_null=True)
    today_sessions = serializers.IntegerField()
    today_units = serializers.IntegerField()
    today_seconds = serializers.FloatField()
    target = TargetSerializer(allow_null=True)
    on_break = serializers.BooleanField()
