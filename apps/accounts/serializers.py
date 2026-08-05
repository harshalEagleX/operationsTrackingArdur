"""Serializers for accounts.

Read and write serializers are separate on purpose. One class that does both
inevitably grows a field an attacker can set — ``role`` being the obvious one.
"""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.models import Employee, LoginHistory, Role, Status, User
from core.validators import validate_emp_id, validate_non_blank


class LoginSerializer(serializers.Serializer):
    """Input only — never echo anything from here back to the client."""

    emp_id = serializers.CharField(max_length=20, validators=[validate_emp_id])
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)


class CurrentUserSerializer(serializers.ModelSerializer):
    """The signed-in user's own profile. Used by /auth/me/ and injected into
    every page as ``current_user``."""

    role = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    is_admin = serializers.BooleanField(read_only=True)
    is_supervisor = serializers.BooleanField(read_only=True)
    project = serializers.SerializerMethodField()
    shift = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "emp_id", "name", "display_name", "role",
            "is_admin", "is_supervisor", "status", "project", "shift", "last_login",
        ]
        read_only_fields = fields

    def get_project(self, obj) -> str:
        return obj.employee.project if obj.employee else ""

    def get_shift(self, obj) -> str:
        return obj.employee.shift if obj.employee else ""


class EmployeeSerializer(serializers.ModelSerializer):
    """Read shape for employee records."""

    has_login = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "id", "employee_id", "name", "email", "phone", "role", "designation",
            "department", "project", "shift", "reporting_to", "date_of_joining",
            "status", "has_login", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "has_login"]

    def get_has_login(self, obj) -> bool:
        return User.objects.filter(emp_id=obj.employee_id).exists()


class EmployeeWriteSerializer(serializers.ModelSerializer):
    """Create / update shape.

    ``max_length`` on every text field is matched to the column width, so an
    over-long value returns 400 instead of being silently truncated into a
    row nobody can find again.
    """

    employee_id = serializers.CharField(max_length=20, validators=[validate_emp_id])
    name = serializers.CharField(max_length=100, validators=[validate_non_blank])
    role = serializers.ChoiceField(choices=Role.choices, default=Role.EMPLOYEE)
    status = serializers.ChoiceField(choices=Status.choices, default=Status.ACTIVE)
    # Optional: set a login password at creation time.
    password = serializers.CharField(
        max_length=128, write_only=True, required=False, allow_blank=True
    )

    class Meta:
        model = Employee
        fields = [
            "employee_id", "name", "email", "phone", "role", "designation",
            "department", "project", "shift", "reporting_to", "date_of_joining",
            "status", "password",
        ]

    def validate_employee_id(self, value: str) -> str:
        qs = Employee.objects.filter(employee_id=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An employee with this ID already exists.")
        return value

    def validate_password(self, value: str) -> str:
        if value:
            validate_password(value)
        return value


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "The two passwords do not match."}
            )
        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError(
                {"new_password": "Choose a password you have not used here before."}
            )
        validate_password(attrs["new_password"])
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    """Admin-driven reset. There is no email round-trip: an ops floor
    supervisor resets a password in person."""

    emp_id = serializers.CharField(max_length=20, validators=[validate_emp_id])
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value: str) -> str:
        validate_password(value)
        return value


class LoginHistorySerializer(serializers.ModelSerializer):
    duration_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = LoginHistory
        fields = [
            "id", "emp_id", "name", "date", "login_time", "logout_time",
            "duration_seconds", "ip_address",
        ]
        read_only_fields = fields
