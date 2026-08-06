"""Work session and target serializers.

Note what the write serializers deliberately do *not* accept: ``start_time``,
``end_time``, ``total_time``, ``average_time``. Those are server-computed. A
client that sends them is ignored rather than trusted.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.tracking.models import SessionState, Target, WorkSession
from core.validators import validate_emp_id, validate_work_units


class WorkSessionSerializer(serializers.ModelSerializer):
    """Read shape."""

    state = serializers.SerializerMethodField()
    live_elapsed_seconds = serializers.FloatField(read_only=True)
    units_per_hour = serializers.FloatField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = WorkSession
        fields = [
            "id", "emp_id", "name", "project", "client_code", "work_type", "batch",
            "work_units", "start_time", "end_time", "total_time", "average_time",
            "is_paused", "paused_at", "paused_elapsed", "allocation_id",
            "is_started", "state", "is_open", "live_elapsed_seconds", "units_per_hour",
            "review", "pages",
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

    work_units = serializers.IntegerField(min_value=0, validators=[validate_work_units])
    review = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    pages = serializers.IntegerField(min_value=0, required=False, allow_null=True, default=None)


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
