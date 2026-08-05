"""Application settings serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.settings_app.models import AppSetting


class AppSettingSerializer(serializers.ModelSerializer):
    typed_value = serializers.SerializerMethodField()

    class Meta:
        model = AppSetting
        fields = [
            "id", "key", "value", "typed_value", "value_type", "label",
            "description", "category", "is_editable", "updated_by", "updated_at",
        ]
        read_only_fields = [
            "id", "key", "typed_value", "value_type", "label",
            "description", "category", "is_editable", "updated_by", "updated_at",
        ]

    def get_typed_value(self, obj):
        return obj.typed_value


class SettingWriteSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=100)
    value = serializers.CharField(max_length=5000, allow_blank=True)
