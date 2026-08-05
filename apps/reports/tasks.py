"""Report background tasks.

Runs on the ``reports`` queue with its own worker, so a 90-second Excel build
never sits in front of a notification fan-out.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.reports.models import ReportJob
from core.timezone import now_ist

logger = logging.getLogger("opstracking.tasks")


@shared_task(bind=True, max_retries=1, soft_time_limit=540)
def build_report_task(self, job_id: int):
    """Generate an export, store it, and tell the requester."""
    from apps.accounts.models import User
    from apps.files.models import FileContext, ScanStatus, StoredFile
    from apps.files.storage import storage_root
    from apps.notifications.services import NotificationService
    from apps.reports.exporters import build_filename, get_exporter
    from apps.reports.selectors import ReportFilters, get_selector
    from apps.reports.services import ReportService

    job = ReportJob.objects.filter(pk=job_id).first()
    if not job:
        logger.error("build_report_task: job %s not found", job_id)
        return {"ok": False, "error": "job not found"}

    actor = User.objects.filter(emp_id=job.requested_by).first()
    service = ReportService(actor=actor)
    service.mark_running(job)

    try:
        filters = ReportFilters.from_params(job.params).scoped_to(actor)
        selector = get_selector(job.report_key, filters)
        rows = selector.rows()

        exporter_class = get_exporter(job.export_format)
        exporter = exporter_class(
            columns=selector.columns, rows=rows, title=job.report_key.title()
        )

        filename = build_filename(job.report_key, job.export_format)
        relative = f"exports/{now_ist():%Y/%m}/{filename}"
        destination = storage_root() / relative

        exporter.write(destination)
        destination.chmod(0o640)

        stored = StoredFile.objects.create(
            owner_emp_id=job.requested_by,
            context=FileContext.EXPORT,
            original_name=filename,
            stored_path=relative,
            mime_type=exporter_class.mime_type,
            size_bytes=destination.stat().st_size,
            sha256=_digest(destination),
            scan_status=ScanStatus.CLEAN,
            claimed_at=now_ist(),
        )

        service.mark_done(job, stored, len(rows))

        NotificationService().notify(
            recipients=[job.requested_by],
            notif_type="report.ready",
            context={"report_key": job.report_key, "rows": len(rows),
                     "body": f"{len(rows)} rows ready to download."},
            link=stored.download_url,
        )

        logger.info("report job %s done: %d rows", job_id, len(rows))
        return {"ok": True, "rows": len(rows), "file_id": stored.id}

    except Exception as exc:
        logger.exception("report job %s failed", job_id)
        service.mark_failed(job, str(exc))

        # Tell the user it failed. A spinner that never resolves is worse than
        # an error message.
        try:
            NotificationService().notify(
                recipients=[job.requested_by],
                notif_type="report.failed",
                context={"report_key": job.report_key,
                         "body": "Please try a narrower date range, or contact support."},
            )
        except Exception:
            logger.exception("could not notify requester of failed report %s", job_id)

        return {"ok": False, "error": str(exc)[:200]}


def _digest(path) -> str:
    import hashlib

    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


@shared_task
def nightly_summary_email():
    """Daily productivity digest for supervisors. Beat, 20:00.

    Not wired to a schedule by default — enable it in the django_celery_beat
    admin once the team decides they want it.
    """
    from apps.accounts.models import Employee
    from apps.notifications.services import NotificationService
    from apps.reports.selectors import ProductivitySelector, ReportFilters
    from core.timezone import today_ist

    filters = ReportFilters(date_from=today_ist(), date_to=today_ist())
    rows = ProductivitySelector(filters).rows()

    total_units = sum(r["total_units"] for r in rows)
    total_hours = sum(r["total_hours"] for r in rows)

    supervisors = list(Employee.objects.supervisors().values_list("employee_id", flat=True))
    if not supervisors:
        return {"sent": 0}

    NotificationService().notify(
        recipients=supervisors,
        notif_type="report.ready",
        context={
            "report_key": "daily summary",
            "body": f"{today_ist():%d %b}: {len(rows)} employees, "
                    f"{total_units} units, {total_hours:.1f} hours.",
        },
        link="/dashboard?tab=reports",
    )
    return {"sent": len(supervisors), "employees": len(rows)}
