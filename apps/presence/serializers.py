"""Presence serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.presence.models import PresenceState, PresenceStatus


class PresenceStateSerializer(serializers.ModelSerializer):
    is_online = serializers.BooleanField(read_only=True)

    class Meta:
        model = PresenceState
        fields = [
            "emp_id", "status", "status_source", "custom_status",
            "is_online", "last_seen_at", "updated_at",
        ]
        read_only_fields = fields


class RosterEntrySerializer(serializers.Serializer):
    """One row of the who's-online rail."""

    emp_id = serializers.CharField()
    name = serializers.CharField()
    role = serializers.CharField()
    project = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    custom_status = serializers.CharField(allow_blank=True)
    last_seen_at = serializers.CharField(allow_null=True)


class SetStatusSerializer(serializers.Serializer):
    """Manual status. Only the three a user may legitimately choose —
    'working' and 'on_break' are derived from real records, not declared."""

    status = serializers.ChoiceField(
        choices=[
            PresenceStatus.ONLINE,
            PresenceStatus.BUSY,
            PresenceStatus.IDLE,
        ]
    )
    custom_status = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
