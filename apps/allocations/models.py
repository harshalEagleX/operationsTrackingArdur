"""Batch allocation and order history models."""

from __future__ import annotations

from django.db import models

from core.managers import OwnedQuerySet
from core.models import legacy_managed
from core.timezone import now_ist


class AllocationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    ON_HOLD = "on_hold", "On hold"
    CANCELLED = "cancelled", "Cancelled"


class Priority(models.TextChoices):
    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


class AllocationQuerySet(OwnedQuerySet):
    owner_field = "employee_id"

    def pending(self):
        return self.filter(status=AllocationStatus.PENDING)

    def open(self):
        return self.filter(
            status__in=(AllocationStatus.PENDING, AllocationStatus.IN_PROGRESS)
        )

    def due_within(self, hours: int):
        """Open allocations whose SLA lands inside the window. Drives the
        breach-warning beat task."""
        from datetime import timedelta

        return self.open().filter(
            due_at__isnull=False,
            due_at__lte=now_ist() + timedelta(hours=hours),
            due_at__gt=now_ist(),
        )

    def overdue(self):
        return self.open().filter(due_at__isnull=False, due_at__lt=now_ist())


class BatchAllocation(models.Model):
    """A batch of work assigned to an employee."""

    id = models.AutoField(primary_key=True)
    allocation_id = models.CharField(max_length=50, unique=True, db_index=True)
    employee_id = models.CharField(max_length=20, db_index=True)
    employee_name = models.CharField(max_length=100, blank=True, default="")

    project = models.CharField(max_length=150, blank=True, default="")
    client_code = models.CharField(max_length=50, blank=True, default="")
    work_type = models.CharField(max_length=100, blank=True, default="")
    batch = models.CharField(max_length=100, blank=True, default="")
    order_id = models.CharField(max_length=100, blank=True, default="", db_index=True)

    quantity = models.IntegerField(default=0)
    completed_quantity = models.IntegerField(default=0)

    status = models.CharField(
        max_length=20, choices=AllocationStatus.choices,
        default=AllocationStatus.PENDING, db_index=True,
    )
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.NORMAL
    )

    allocated_at = models.DateTimeField(default=now_ist)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    allocated_by = models.CharField(max_length=20, blank=True, default="")
    remarks = models.CharField(max_length=500, blank=True, default="")
    sla_notified = models.BooleanField(default=False)

    objects = AllocationQuerySet.as_manager()

    class Meta:
        managed = legacy_managed()
        db_table = "ot_batch_allocations"
        ordering = ["-allocated_at"]
        indexes = [
            models.Index(fields=["employee_id", "status"], name="ix_alloc_emp_status"),
            models.Index(fields=["status", "due_at"], name="ix_alloc_status_due"),
        ]

    def __str__(self) -> str:
        return f"{self.allocation_id} → {self.employee_id} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in (AllocationStatus.PENDING, AllocationStatus.IN_PROGRESS)

    @property
    def progress_percent(self) -> float:
        if not self.quantity:
            return 0.0
        return round(min(self.completed_quantity / self.quantity * 100, 100), 1)

    @property
    def is_overdue(self) -> bool:
        return bool(self.due_at) and self.is_open and self.due_at < now_ist()


class OrderHistory(models.Model):
    """Append-only audit trail of what happened to an allocation.

    Never updated, only inserted — an audit trail you can edit is not one.
    """

    id = models.AutoField(primary_key=True)
    allocation_id = models.CharField(max_length=50, db_index=True)
    order_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    employee_id = models.CharField(max_length=20, blank=True, default="", db_index=True)
    action = models.CharField(max_length=50)
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20, blank=True, default="")
    quantity = models.IntegerField(null=True, blank=True)
    remarks = models.CharField(max_length=500, blank=True, default="")
    performed_by = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(default=now_ist, db_index=True)

    class Meta:
        managed = legacy_managed()
        db_table = "ot_orders_history"
        ordering = ["-created_at"]
        verbose_name_plural = "order history"

    def __str__(self) -> str:
        return f"{self.allocation_id}: {self.action} @ {self.created_at:%Y-%m-%d %H:%M}"


class OrderRate(models.Model):
    """Vendor rates and SLAs for order types across states and counties."""

    id = models.AutoField(primary_key=True)
    order_type = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    stateabr = models.CharField(max_length=100, blank=True, default="")
    county = models.CharField(max_length=100)
    vendor_rts = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    eta_rts = models.IntegerField(blank=True, null=True)
    vendor_slt = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    eta_slt = models.IntegerField(blank=True, null=True)
    remark = models.CharField(max_length=250, blank=True, default="")

    class Meta:
        managed = legacy_managed()
        db_table = "ot_order_rates"
        ordering = ["order_type", "state", "county"]

    def __str__(self) -> str:
        return f"{self.order_type} - {self.state} - {self.county}"
