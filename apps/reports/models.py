"""Async export job tracking.

Generating a 50,000-row Excel file inside a request holds a web worker for 60
to 120 seconds. Five concurrent exports and the whole application stops
responding. The request creates a job row, returns 202, and a Celery worker
does the work — this is the single highest-leverage performance decision in
the whole design.
"""

from __future__ import annotations

from django.db import models

from core.timezone import now_ist


class JobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"


class ReportJob(models.Model):
    id = models.BigAutoField(primary_key=True)
    requested_by = models.CharField(max_length=20, db_index=True)
    report_key = models.CharField(max_length=60)
    params = models.JSONField(default=dict)
    export_format = models.CharField(max_length=10, default="xlsx")

    status = models.CharField(
        max_length=10, choices=JobStatus.choices, default=JobStatus.QUEUED, db_index=True
    )
    file = models.ForeignKey(
        "files.StoredFile", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="report_jobs",
    )
    row_count = models.IntegerField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True, default="")

    created_at = models.DateTimeField(default=now_ist, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ot_report_jobs"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["requested_by", "-id"], name="ix_reportjob_user"),
        ]

    def __str__(self) -> str:
        return f"{self.report_key} for {self.requested_by} ({self.status})"

    @property
    def is_finished(self) -> bool:
        return self.status in (JobStatus.DONE, JobStatus.FAILED)

    @property
    def duration_seconds(self) -> float | None:
        if not self.started_at or not self.finished_at:
            return None
        from core.timezone import elapsed_seconds

        return elapsed_seconds(self.started_at, self.finished_at)

    @property
    def download_url(self) -> str | None:
        return self.file.download_url if self.file else None
