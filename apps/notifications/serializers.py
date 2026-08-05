"""Notification serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.notifications.models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id", "notif_type", "title", "body", "payload", "link_url",
            "priority", "actor_emp_id", "read_at", "is_read", "created_at",
        ]
        read_only_fields = fields


class MarkReadSerializer(serializers.Serializer):
    """Omit ``ids`` to mark everything read."""

    ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True, default=list
    )


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    description = serializers.SerializerMethodField()

    class Meta:
        model = NotificationPreference
        fields = ["id", "notif_type", "in_app", "email", "description"]
        read_only_fields = ["id", "description"]

    def get_description(self, obj) -> str:
        from apps.notifications.registry import REGISTRY

        spec = REGISTRY.get(obj.notif_type)
        return spec.description if spec else ""


class PreferenceWriteSerializer(serializers.Serializer):
    notif_type = serializers.CharField(max_length=60)
    in_app = serializers.BooleanField(default=True)
    email = serializers.BooleanField(default=False)

    def validate_notif_type(self, value: str) -> str:
        from apps.notifications.registry import REGISTRY

        if value not in REGISTRY:
            raise serializers.ValidationError("Unknown notification type.")
        return value
