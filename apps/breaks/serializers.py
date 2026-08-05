"""Break serializers.

``StartBreakSerializer`` has exactly one field. There is deliberately no
``allotted_time`` — that value is the server's, and a field the client can
send is a field the client can lie about.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.breaks.constants import BREAK_ALLOWANCES
from apps.breaks.models import BreakTime


class BreakSerializer(serializers.ModelSerializer):
    emp_id = serializers.CharField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    live_elapsed_seconds = serializers.FloatField(read_only=True)
    remaining_seconds = serializers.FloatField(read_only=True)
    overrun_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = BreakTime
        fields = [
            "id", "emp_id", "user_id", "user_name", "break_type",
            "start_time", "end_time", "total_time", "allotted_time",
            "is_overrun", "is_open", "live_elapsed_seconds",
            "remaining_seconds", "overrun_seconds",
        ]
        read_only_fields = fields


class StartBreakSerializer(serializers.Serializer):
    break_type = serializers.ChoiceField(choices=list(BREAK_ALLOWANCES.keys()))


class EndBreakSerializer(serializers.Serializer):
    """``break_id`` is optional — "end whatever I have open" is the normal
    case and survives a tab reload."""

    break_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class BreakTypeSerializer(serializers.Serializer):
    """The catalogue the UI renders its buttons from."""

    break_type = serializers.CharField()
    allotted_seconds = serializers.IntegerField()
    allotted_minutes = serializers.IntegerField()
    repeatable = serializers.BooleanField()
    taken_today = serializers.BooleanField()
