"""Allocation serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.allocations.models import (
    AllocationStatus,
    BatchAllocation,
    OrderHistory,
    Priority,
)
from core.validators import validate_emp_id


class AllocationSerializer(serializers.ModelSerializer):
    progress_percent = serializers.FloatField(read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = BatchAllocation
        fields = [
            "id", "allocation_id", "employee_id", "employee_name",
            "project", "client_code", "work_type", "batch", "order_id",
            "quantity", "completed_quantity", "progress_percent",
            "status", "priority", "allocated_at", "due_at", "started_at",
            "completed_at", "allocated_by", "remarks", "is_overdue", "is_open",
        ]
        read_only_fields = [
            "id", "progress_percent", "is_overdue", "is_open",
            "allocated_by", "allocated_at", "started_at", "completed_at",
        ]


class AllocationWriteSerializer(serializers.ModelSerializer):
    allocation_id = serializers.CharField(max_length=50)
    employee_id = serializers.CharField(max_length=20, validators=[validate_emp_id])
    quantity = serializers.IntegerField(min_value=1, max_value=1_000_000)
    priority = serializers.ChoiceField(choices=Priority.choices, default=Priority.NORMAL)

    class Meta:
        model = BatchAllocation
        fields = [
            "allocation_id", "employee_id", "employee_name", "project",
            "client_code", "work_type", "batch", "order_id", "quantity",
            "priority", "due_at", "remarks",
        ]

    def validate_employee_id(self, value: str) -> str:
        from apps.accounts.models import Employee

        if not Employee.objects.filter(employee_id=value, status="active").exists():
            raise serializers.ValidationError("No active employee with that ID.")
        return value

    def validate_due_at(self, value):
        from core.timezone import now_ist

        if value and value < now_ist():
            raise serializers.ValidationError("The due date cannot be in the past.")
        return value


class AllocationStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=AllocationStatus.choices)
    completed_quantity = serializers.IntegerField(
        min_value=0, required=False, allow_null=True, default=None
    )
    remarks = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class ReassignSerializer(serializers.Serializer):
    employee_id = serializers.CharField(max_length=20, validators=[validate_emp_id])
    employee_name = serializers.CharField(max_length=100, required=False,
                                          allow_blank=True, default="")


class OrderHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderHistory
        fields = [
            "id", "allocation_id", "order_id", "employee_id", "action",
            "from_status", "to_status", "quantity", "remarks",
            "performed_by", "created_at",
        ]
        read_only_fields = fields
