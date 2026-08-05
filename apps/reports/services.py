"""Report services."""

from __future__ import annotations

import logging

from django.db import transaction

from apps.reports.models import JobStatus, ReportJob
from apps.reports.selectors import REPORT_REGISTRY, ReportFilters, get_selector
from core.exceptions import ValidationError
from core.services import BaseService
from core.timezone import now_ist

logger = logging.getLogger("opstracking.reports")

MAX_INLINE_ROWS = 5000


class ReportService(BaseService):
    """Run reports inline, or queue an export."""

    def run(self, report_key: str, params: dict) -> dict:
        """Execute a report and return its rows.

        For the on-screen table. Anything large enough to be slow should be
        exported instead — see ``queue_export``.
        """
        filters = ReportFilters.from_params(params).scoped_to(self.actor)
        selector = get_selector(report_key, filters)

        rows = selector.rows()

        truncated = len(rows) > MAX_INLINE_ROWS
        if truncated:
            rows = rows[:MAX_INLINE_ROWS]

        return {
            "report_key": report_key,
            "columns": [{"key": key, "label": label} for key, label in selector.columns],
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }

    @transaction.atomic
    def queue_export(self, report_key: str, params: dict, export_format: str = "xlsx") -> ReportJob:
        """Create a job and hand it to a worker.

        Returns immediately with 202. When the worker finishes it stores the
        file and sends a ``report.ready`` notification, which arrives on the
        user's screen as a toast with a download link.
        """
        self.require_actor()

        if report_key not in REPORT_REGISTRY:
            raise ValidationError(
                f"Unknown report '{report_key}'. "
                f"Available: {', '.join(sorted(REPORT_REGISTRY))}"
            )

        if export_format not in ("xlsx", "csv"):
            raise ValidationError("Export format must be xlsx or csv.")

        job = ReportJob.objects.create(
            requested_by=self.actor.emp_id,
            report_key=report_key,
            params=params,
            export_format=export_format,
            created_at=now_ist(),
        )

        from apps.reports.tasks import build_report_task

        self.on_commit(lambda: build_report_task.delay(job.id))

        self.log("export_queued", job=job.id, report=report_key)
        return job

    def get_job(self, job_id: int) -> ReportJob:
        """Fetch a job, refusing to show someone else's."""
        job = self.require_found(
            ReportJob.objects.filter(pk=job_id).first(), "No such export job."
        )
        self.require_owner_or_supervisor(job.requested_by, "That export belongs to someone else.")
        return job

    def mark_running(self, job: ReportJob) -> None:
        ReportJob.objects.filter(pk=job.pk).update(
            status=JobStatus.RUNNING, started_at=now_ist()
        )

    def mark_done(self, job: ReportJob, stored_file, row_count: int) -> None:
        ReportJob.objects.filter(pk=job.pk).update(
            status=JobStatus.DONE,
            file=stored_file,
            row_count=row_count,
            finished_at=now_ist(),
        )

    def mark_failed(self, job: ReportJob, message: str) -> None:
        ReportJob.objects.filter(pk=job.pk).update(
            status=JobStatus.FAILED,
            error_message=str(message)[:500],
            finished_at=now_ist(),
        )
