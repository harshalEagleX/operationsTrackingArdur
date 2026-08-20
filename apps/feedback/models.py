"""Quality feedback and its attached images.

The legacy ``ot_feedback_images`` table stored image bytes in a BLOB column.
That bloats every backup, evicts real data from the InnoDB buffer pool, and
makes mysqldump unusable. The ``file`` foreign key below points at
apps.files.StoredFile instead; ``image_data`` is kept nullable purely so
existing rows can be migrated out with
``manage.py migrate_feedback_images`` and the column then dropped.
"""

from __future__ import annotations

from django.db import models

from core.managers import OwnedQuerySet
from core.models import legacy_managed
from core.timezone import now_ist


class FeedbackType(models.TextChoices):
    QUALITY = "quality", "Quality"
    AUDIT = "audit", "Audit"
    COACHING = "coaching", "Coaching"
    APPRECIATION = "appreciation", "Appreciation"


class Severity(models.TextChoices):
    INFO = "info", "Informational"
    MINOR = "minor", "Minor"
    MAJOR = "major", "Major"
    CRITICAL = "critical", "Critical"


class FeedbackQuerySet(OwnedQuerySet):
    owner_field = "emp_id"

    def visible_to(self, user):
        """Employees see feedback *about themselves* and feedback they wrote.

        A plain owner filter would hide the coaching note a team lead wrote,
        from the team lead. Supervisors see everything.
        """
        if user is None or not user.is_authenticated:
            return self.none()
        if user.is_supervisor:
            return self
        return self.filter(models.Q(emp_id=user.emp_id) | models.Q(created_by=user.emp_id))

    def unacknowledged(self):
        return self.filter(acknowledged_at__isnull=True)


class Feedback(models.Model):
    id = models.AutoField(primary_key=True)
    emp_id = models.CharField(max_length=50, db_index=True, help_text="Who the feedback is about")
    emp_name = models.CharField(max_length=100, blank=True, default="")

    feedback_type = models.CharField(
        max_length=20, choices=FeedbackType.choices, default=FeedbackType.QUALITY, blank=True
    )
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.INFO, blank=True
    )

    project = models.CharField(max_length=150, blank=True, default="")
    client_code = models.CharField(max_length=150, blank=True, default="")
    order_batch_id = models.CharField(max_length=100, blank=True, default="", null=True, db_index=True)
    work_type = models.CharField(max_length=150, blank=True, default="")

    feedback_recorded = models.CharField(max_length=50, blank=True, default="internalAudit")
    processed_date = models.DateField(null=True, blank=True)
    feedback_received_date = models.DateField(null=True, blank=True)
    feedback_received_mode = models.CharField(max_length=50, blank=True, default="email")
    feedback_provided_by = models.CharField(max_length=100, blank=True, default="")
    feedback = models.TextField(blank=True, default="")
    type = models.CharField(max_length=100, blank=True, default="")
    comments = models.TextField(blank=True, default="", null=True)
    action_taken = models.TextField(blank=True, default="", null=True)
    status = models.CharField(max_length=20, blank=True, default="open")
    open_date = models.DateField(null=True, blank=True)
    closure_date = models.DateField(null=True, blank=True)

    subject = models.CharField(max_length=200, blank=True, default="")
    description = models.TextField(blank=True, default="", null=True)
    error_count = models.IntegerField(default=0, null=True, blank=True)
    sample_size = models.IntegerField(default=0, null=True, blank=True)

    created_by = models.CharField(max_length=50, blank=True, default="", null=True, db_index=True)
    created_by_name = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(default=now_ist, db_index=True, null=True, blank=True)
    updated_by = models.CharField(max_length=50, blank=True, default="", null=True)
    updated_at = models.DateTimeField(default=now_ist, null=True, blank=True)

    acknowledgment = models.IntegerField(null=True, blank=True)
    acknowledgment_comment = models.TextField(blank=True, default="", null=True)
    acknowledgment_date = models.DateTimeField(null=True, blank=True)

    acknowledged_at = models.DateTimeField(null=True, blank=True)
    response = models.TextField(blank=True, default="", null=True)

    objects = FeedbackQuerySet.as_manager()

    class Meta:
        managed = legacy_managed()
        db_table = "ot_feedbacks"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["emp_id", "created_at"], name="ix_fb_emp_created"),
            models.Index(fields=["order_batch_id"], name="ix_fb_batch"),
        ]
        verbose_name_plural = "feedback"

    def __str__(self) -> str:
        return f"{self.feedback_type or self.type} for {self.emp_id}: {self.subject or self.feedback}"

    @property
    def is_acknowledged(self) -> bool:
        return self.acknowledged_at is not None or self.acknowledgment == 1

    @property
    def accuracy_percent(self) -> float | None:
        if not self.sample_size:
            return None
        return round((1 - (self.error_count or 0) / self.sample_size) * 100, 2)


class FeedbackImage(models.Model):
    """An image attached to a feedback record."""

    id = models.AutoField(primary_key=True)
    feedback = models.ForeignKey(
        Feedback, on_delete=models.CASCADE, related_name="images", db_column="feedback_id"
    )
    file = models.ForeignKey(
        "files.StoredFile", on_delete=models.PROTECT,
        null=True, blank=True, related_name="feedback_images",
    )
    caption = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=now_ist)

    # Legacy BLOB. Nullable, deprecated, migrated out by
    # `manage.py migrate_feedback_images`, then droppable.
    image_data = models.BinaryField(null=True, blank=True, editable=False)

    class Meta:
        managed = legacy_managed()
        db_table = "ot_feedback_images"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"image {self.id} on feedback {self.feedback_id}"
