"""Work session and target models.

``ot_user_work_data`` is the busiest table in the application and the source
for every productivity report — the indexes on it are not optional.
"""

from __future__ import annotations

from django.db import models

from core.managers import OwnedQuerySet
from core.models import legacy_managed
from core.timezone import elapsed_seconds, now_ist


class SessionState(models.IntegerChoices):
    """The legacy ``is_started`` column, given names.

    A bare 0/1/2 in application code is how a report ends up counting
    allocated-but-not-started work as completed.
    """

    ALLOCATED = 0, "Allocated"
    RUNNING = 1, "Running"
    COMPLETED = 2, "Completed"


class WorkSessionQuerySet(OwnedQuerySet):
    owner_field = "emp_id"

    def open(self):
        """Started and not yet ended."""
        return self.filter(end_time__isnull=True, is_started=SessionState.RUNNING)

    def completed(self):
        return self.filter(is_started=SessionState.COMPLETED, end_time__isnull=False)

    def active_now(self):
        """Running and not paused — what 'currently working' means for presence."""
        return self.open().filter(is_paused=False)

    def for_day(self, day=None):
        from core.timezone import day_bounds

        start, end = day_bounds(day)
        return self.filter(start_time__gte=start, start_time__lt=end)

    def between(self, start, end):
        queryset = self
        if start:
            queryset = queryset.filter(start_time__gte=start)
        if end:
            queryset = queryset.filter(start_time__lt=end)
        return queryset


class WorkSession(models.Model):
    """One unit of tracked work: start, optional pauses, end, units produced."""

    id = models.AutoField(primary_key=True)
    emp_id = models.CharField(max_length=20, db_index=True)
    name = models.CharField(max_length=100, blank=True, default="")
    project = models.CharField(max_length=150, blank=True, default="")
    client_code = models.CharField(max_length=50, blank=True, default="")
    work_type = models.CharField(max_length=100, blank=True, default="")
    batch = models.CharField(max_length=100, blank=True, default="")
    work_units = models.IntegerField(default=0)

    start_time = models.DateTimeField(default=now_ist)
    end_time = models.DateTimeField(null=True, blank=True)
    total_time = models.FloatField(null=True, blank=True, help_text="Seconds, excluding pauses")
    average_time = models.FloatField(null=True, blank=True, help_text="Seconds per work unit")

    is_paused = models.BooleanField(default=False)
    paused_at = models.DateTimeField(null=True, blank=True)
    paused_by = models.CharField(max_length=20, blank=True, default="")
    paused_elapsed = models.FloatField(default=0, help_text="Total seconds spent paused")

    # null=True matches the existing column: NULL means "ad-hoc work, not
    # against any allocation", which is different from an empty string.
    allocation_id = models.CharField(  # noqa: DJ001
        max_length=50, null=True, blank=True, db_index=True
    )
    is_started = models.SmallIntegerField(
        choices=SessionState.choices, default=SessionState.ALLOCATED, db_index=True
    )

    review = models.CharField(max_length=255, blank=True, default="")
    pages = models.IntegerField(null=True, blank=True)

    objects = WorkSessionQuerySet.as_manager()

    class Meta:
        managed = legacy_managed()
        db_table = "ot_user_work_data"
        ordering = ["-start_time"]
        indexes = [
            # These three are the difference between a 40ms and a 4s report.
            models.Index(fields=["emp_id", "start_time"], name="ix_work_emp_start"),
            models.Index(fields=["is_started", "start_time"], name="ix_work_started"),
            models.Index(fields=["project", "start_time"], name="ix_work_project"),
        ]
        constraints = [
            # WorkSessionService.start_session() locks on the same condition
            # before inserting, but that lock has nothing to hold when no row
            # exists yet — two concurrent "Start work" clicks from a cold
            # state both see "nothing open" and both insert. Only the
            # database can settle that race; this is the same pattern
            # BreakTime uses (uq_one_open_break_per_user).
            models.UniqueConstraint(
                fields=["emp_id"],
                condition=models.Q(end_time__isnull=True, is_started=SessionState.RUNNING),
                name="uq_one_open_session_per_emp",
            )
        ]

    def __str__(self) -> str:
        return f"{self.emp_id} · {self.work_type} · {self.start_time:%Y-%m-%d %H:%M}"

    # ── derived, never stored twice ──────────────────────────

    @property
    def is_open(self) -> bool:
        return self.end_time is None and self.is_started == SessionState.RUNNING

    @property
    def live_elapsed_seconds(self) -> float:
        """Elapsed working time right now, for an open session.

        Computed server-side so a UI timer and a report can never disagree.
        While paused, the clock stops at ``paused_at``.
        """
        if self.end_time:
            return self.total_time or 0.0

        reference = self.paused_at if self.is_paused else now_ist()
        gross = elapsed_seconds(self.start_time, reference)
        return max(gross - (self.paused_elapsed or 0), 0.0)

    @property
    def units_per_hour(self) -> float | None:
        if not self.total_time or not self.work_units:
            return None
        return round(self.work_units / (self.total_time / 3600), 2)


class TargetQuerySet(OwnedQuerySet):
    owner_field = "emp_id"

    def for_day(self, day=None):
        from core.timezone import today_ist

        return self.filter(target_date=day or today_ist())


class Target(models.Model):
    """A daily work-unit target, per employee and project."""

    id = models.AutoField(primary_key=True)
    emp_id = models.CharField(max_length=20, db_index=True)
    project = models.CharField(max_length=150, blank=True, default="")
    work_type = models.CharField(max_length=100, blank=True, default="")
    target_date = models.DateField(db_index=True)
    target_units = models.IntegerField(default=0)
    achieved_units = models.IntegerField(default=0)
    created_by = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(default=now_ist)
    updated_at = models.DateTimeField(default=now_ist)

    objects = TargetQuerySet.as_manager()

    class Meta:
        managed = legacy_managed()
        db_table = "ot_targets"
        ordering = ["-target_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["emp_id", "project", "work_type", "target_date"],
                name="uq_target_emp_day",
            )
        ]

    def __str__(self) -> str:
        return f"{self.emp_id} {self.target_date}: {self.achieved_units}/{self.target_units}"

    @property
    def completion_percent(self) -> float:
        if not self.target_units:
            return 0.0
        return round(min(self.achieved_units / self.target_units * 100, 999), 1)

    @property
    def is_met(self) -> bool:
        return bool(self.target_units) and self.achieved_units >= self.target_units
