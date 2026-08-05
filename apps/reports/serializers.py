"""Report serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.reports.models import ReportJob
from apps.reports.selectors import REPORT_REGISTRY


class ReportRunSerializer(serializers.Serializer):
    report_key = serializers.ChoiceField(choices=sorted(REPORT_REGISTRY.keys()))
    date_from = serializers.DateField(required=False, allow_null=True, default=None)
    date_to = serializers.DateField(required=False, allow_null=True, default=None)
    emp_ids = serializers.ListField(
        child=serializers.CharField(max_length=20), required=False, default=list
    )
    projects = serializers.ListField(
        child=serializers.CharField(max_length=150), required=False, default=list
    )
    work_types = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, default=list
    )

    def validate(self, attrs):
        date_from, date_to = attrs.get("date_from"), attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {"date_to": "The end date must be on or after the start date."}
            )
        return attrs


class ReportExportSerializer(ReportRunSerializer):
    export_format = serializers.ChoiceField(choices=["xlsx", "csv"], default="xlsx")


class ReportJobSerializer(serializers.ModelSerializer):
    download_url = serializers.CharField(read_only=True, allow_null=True)
    duration_seconds = serializers.FloatField(read_only=True, allow_null=True)
    is_finished = serializers.BooleanField(read_only=True)

    class Meta:
        model = ReportJob
        fields = [
            "id", "report_key", "params", "export_format", "status",
            "row_count", "error_message", "download_url", "duration_seconds",
            "is_finished", "created_at", "started_at", "finished_at",
        ]
        read_only_fields = fields


class ReportCatalogueSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    columns = serializers.ListField(child=serializers.DictField())
