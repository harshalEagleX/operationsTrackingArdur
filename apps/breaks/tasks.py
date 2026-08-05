"""Break background tasks."""

from __future__ import annotations

import logging

from celery import shared_task

from apps.breaks.constants import OVERRUN_GRACE_SECONDS
from apps.breaks.models import BreakTime

logger = logging.getLogger("opstracking.tasks")


@shared_task
def check_break_overruns():
    """Alert on breaks that have run past their allowance. Beat, every minute.

    ``overrun_notified`` makes this idempotent — the employee gets one message
    per break, not one per minute for the rest of the afternoon.
    """
    from apps.accounts.models import Employee
    from apps.notifications.services import NotificationService

    overrunning = BreakTime.objects.overrunning(OVERRUN_GRACE_SECONDS).filter(
        overrun_notified=False
    )

    notified = 0
    for brk in overrunning.iterator():
        try:
            supervisor_ids = list(
                Employee.objects.supervisors().values_list("employee_id", flat=True)
            )

            NotificationService().notify(
                recipients=[brk.user_id, *supervisor_ids],
                notif_type="break.overrun",
                context={
                    "break_type": brk.break_type,
                    "allotted": (brk.allotted_time or 0) // 60,
                    "emp_id": brk.user_id,
                    "name": brk.user_name or brk.user_id,
                    "body": f"{brk.user_name or brk.user_id} has been on "
                            f"{brk.break_type} for {int(brk.live_elapsed_seconds // 60)} minutes.",
                },
                link=f"/dashboard?tab=breaks&emp_id={brk.user_id}",
            )

            BreakTime.objects.filter(pk=brk.pk).update(is_overrun=True, overrun_notified=True)
            notified += 1
        except Exception:
            logger.exception("failed to raise overrun alert for break %s", brk.pk)

    if notified:
        logger.info("raised %d break-overrun alerts", notified)
    return {"notified": notified}


@shared_task
def close_abandoned_breaks(max_hours: int = 8):
    """Close breaks nobody ever ended.

    A break left open overnight would otherwise show the employee as
    permanently on_break and corrupt tomorrow's break report.
    """
    from datetime import timedelta

    from core.timezone import now_ist

    cutoff = now_ist() - timedelta(hours=max_hours)
    abandoned = BreakTime.objects.open().filter(start_time__lt=cutoff)

    closed = 0
    for brk in abandoned.iterator():
        # Credit only the allowance, not the whole overnight gap — the
        # employee did not actually take an eleven-hour tea break.
        brk.end_time = brk.start_time + timedelta(seconds=brk.allotted_time or 0)
        brk.total_time = float(brk.allotted_time or 0)
        brk.is_overrun = True
        brk.save(update_fields=["end_time", "total_time", "is_overrun"])
        closed += 1

    if closed:
        logger.warning("auto-closed %d abandoned breaks older than %dh", closed, max_hours)
    return {"closed": closed}
