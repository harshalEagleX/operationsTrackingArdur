"""Feedback serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.feedback.models import Feedback, FeedbackImage, FeedbackType, Severity
from core.validators import validate_emp_id, validate_non_blank


class FeedbackImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    thumb_url = serializers.SerializerMethodField()

    class Meta:
        model = FeedbackImage
        fields = ["id", "caption", "url", "thumb_url", "created_at"]
        read_only_fields = fields

    def get_url(self, obj) -> str | None:
        return obj.file.download_url if obj.file else None

    def get_thumb_url(self, obj) -> str | None:
        return obj.file.thumbnail_url if obj.file else None


class FeedbackSerializer(serializers.ModelSerializer):
    images = FeedbackImageSerializer(many=True, read_only=True)
    is_acknowledged = serializers.BooleanField(read_only=True)
    accuracy_percent = serializers.FloatField(read_only=True)

    class Meta:
        model = Feedback
        fields = [
            "id", "emp_id", "emp_name", "feedback_type", "severity",
            "project", "client_code", "order_batch_id", "work_type",
            "feedback_recorded", "processed_date", "feedback_received_date",
            "feedback_received_mode", "feedback_provided_by", "feedback",
            "type", "comments", "action_taken", "status",
            "open_date", "closure_date",
            "subject", "description",
            "error_count", "sample_size", "accuracy_percent",
            "created_by", "created_by_name", "created_at",
            "updated_by", "updated_at",
            "acknowledgment", "acknowledgment_comment", "acknowledgment_date",
            "acknowledged_at", "is_acknowledged", "response", "images",
        ]
        read_only_fields = [
            "id", "created_by", "created_by_name", "created_at",
            "updated_by", "updated_at", "acknowledgment_date",
            "acknowledged_at", "is_acknowledged",
            "images", "accuracy_percent",
        ]


class FeedbackWriteSerializer(serializers.ModelSerializer):
    emp_id = serializers.CharField(max_length=50, validators=[validate_emp_id])
    subject = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    feedback_type = serializers.CharField(max_length=20, required=False, allow_blank=True, default=FeedbackType.QUALITY)
    severity = serializers.CharField(max_length=20, required=False, allow_blank=True, default=Severity.INFO)
    # Upload first via /api/v1/files/, then reference the ids here.
    file_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, write_only=True, default=list,
    )

    class Meta:
        model = Feedback
        fields = [
            "emp_id", "emp_name", "feedback_type", "severity", "project", "client_code",
            "order_batch_id", "work_type", "feedback_recorded", "processed_date",
            "feedback_received_date", "feedback_received_mode", "feedback_provided_by",
            "feedback", "type", "comments", "action_taken", "status",
            "open_date", "closure_date", "acknowledgment", "acknowledgment_comment",
            "subject", "description", "error_count", "sample_size", "file_ids",
        ]

    def validate_emp_id(self, value: str) -> str:
        from apps.accounts.models import Employee

        if not Employee.objects.filter(employee_id=value).exists():
            raise serializers.ValidationError("No employee with that ID.")
        return value

    def validate(self, attrs):
        errors = attrs.get("error_count", 0)
        sample = attrs.get("sample_size", 0)
        if sample and errors and errors > sample:
            raise serializers.ValidationError(
                {"error_count": "The error count cannot exceed the sample size."}
            )
        return attrs


class AcknowledgeSerializer(serializers.Serializer):
    response = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )
