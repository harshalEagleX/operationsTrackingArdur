"""Account models, mapped onto the tables inherited from the Flask app.

Table names are preserved exactly (ot_users, ot_employees,
ot_user_login_history) so a DBA browsing the schema sees one coherent
application and so both applications can run side by side during cutover.

Whether Django owns the schema is environment-driven — see
core.models.legacy_managed().
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db import models

from apps.accounts.managers import EmployeeManager, LoginHistoryManager, UserManager
from core.models import legacy_managed
from core.timezone import now_ist


class Role(models.TextChoices):
    ADMIN = "admin", "Administrator"
    SUPERVISOR = "supervisor", "Supervisor"
    EMPLOYEE = "employee", "Employee"


class Status(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"


class User(AbstractBaseUser):
    """Authentication identity, on the existing ot_users table.

    No PermissionsMixin: it would demand auth_group / auth_permission M2M
    tables this application has no use for. Authorisation is role-based, and
    the role lives on Employee.
    """

    id = models.AutoField(primary_key=True)
    emp_id = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=100, blank=True, default="")
    password = models.CharField(max_length=255)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    # Written for one release cycle so any residual Flask-era code stays
    # consistent during cutover, then the column can be dropped.
    # null=True matches the existing column, which distinguishes "no active
    # session" (NULL) from "" — the Flask app relies on that during cutover.
    session_id = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    last_login = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "emp_id"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    class Meta:
        managed = legacy_managed()
        db_table = "ot_users"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return f"{self.emp_id} ({self.name})" if self.name else self.emp_id

    # ── role, derived from ot_employees ──────────────────────
    # Cached per instance: the role is read several times per request (by the
    # permission class, the serializer, the template) and it cannot change
    # mid-request.

    _employee_cache = None

    @property
    def employee(self):
        if self._employee_cache is None:
            self._employee_cache = Employee.objects.filter(employee_id=self.emp_id).first()
        return self._employee_cache

    @property
    def role(self) -> str:
        employee = self.employee
        return (employee.role if employee else Role.EMPLOYEE).lower()

    @property
    def display_name(self) -> str:
        return self.name or (self.employee.name if self.employee else self.emp_id)

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_supervisor(self) -> bool:
        """Supervisor *or above* — admins are supervisors for every purpose."""
        return self.role in (Role.ADMIN, Role.SUPERVISOR)

    @property
    def is_active(self) -> bool:
        return self.status == Status.ACTIVE

    # ── django admin compatibility, without PermissionsMixin ──

    @property
    def is_staff(self) -> bool:
        return self.is_admin

    @property
    def is_superuser(self) -> bool:
        return self.is_admin

    def has_perm(self, perm, obj=None) -> bool:
        return self.is_admin

    def has_module_perms(self, app_label) -> bool:
        return self.is_admin


class Employee(models.Model):
    """The business record: name, role, project, shift.

    Kept separate from User because the two have genuinely different
    lifecycles — an employee exists in reports long after their login is
    disabled.
    """

    id = models.AutoField(primary_key=True)
    employee_id = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=150, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.EMPLOYEE, db_index=True
    )
    designation = models.CharField(max_length=100, blank=True, default="")
    department = models.CharField(max_length=100, blank=True, default="", db_column="work_location")
    project = models.CharField(max_length=150, blank=True, default="", db_column="projects")
    shift = models.CharField(max_length=50, blank=True, default="", db_column="shift_time")
    reporting_to = models.CharField(max_length=20, blank=True, default="")
    date_of_joining = models.DateField(null=True, blank=True, db_column="joining_date")
    
    # Legacy fields heavily used by the app but missing from OOP rewrite
    client_code = models.CharField(max_length=150, blank=True, default="")
    work_type = models.CharField(max_length=150, blank=True, default="")
    active_inactive_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    created_at = models.DateTimeField(default=now_ist)
    updated_at = models.DateTimeField(default=now_ist)

    objects = EmployeeManager()

    class Meta:
        managed = legacy_managed()
        db_table = "ot_employees"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["role", "status"], name="ix_emp_role_status"),
            models.Index(fields=["project"], name="ix_emp_project"),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} — {self.name}"

    @property
    def is_supervisor(self) -> bool:
        return self.role in (Role.ADMIN, Role.SUPERVISOR)


class LoginHistory(models.Model):
    """One row per session. The logout_time is filled in by AuthService."""

    id = models.AutoField(primary_key=True)
    emp_id = models.CharField(max_length=20, db_index=True)
    name = models.CharField(max_length=100, blank=True, default="")
    date = models.DateField(default=None, null=True, blank=True)
    login_time = models.DateTimeField(default=now_ist)
    logout_time = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    session_key = models.CharField(max_length=64, blank=True, default="")

    objects = LoginHistoryManager()

    class Meta:
        managed = legacy_managed()
        db_table = "ot_user_login_history"
        ordering = ["-login_time"]
        indexes = [
            models.Index(fields=["emp_id", "date"], name="ix_login_emp_date"),
            models.Index(fields=["logout_time"], name="ix_login_open"),
        ]
        verbose_name_plural = "login history"

    def __str__(self) -> str:
        return f"{self.emp_id} @ {self.login_time:%Y-%m-%d %H:%M}"

    @property
    def duration_seconds(self) -> float | None:
        if not self.logout_time:
            return None
        from core.timezone import elapsed_seconds

        return elapsed_seconds(self.login_time, self.logout_time)
