"""Background tasks for accounts."""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from apps.accounts.models import Employee, LoginHistory
from core.timezone import now_ist, today_ist

logger = logging.getLogger("opstracking.tasks")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email(self, employee_id: str):
    """Mail a newly created employee their account details."""
    employee = Employee.objects.filter(employee_id=employee_id).first()
    if not employee or not employee.email:
        return {"sent": False, "reason": "no email on record"}

    try:
        send_mail(
            subject="Your OpsTracking account",
            message=(
                f"Hello {employee.name},\n\n"
                f"An OpsTracking account has been created for you.\n"
                f"Your employee ID is {employee.employee_id}.\n\n"
                f"Your supervisor will give you your initial password. "
                f"Please change it after you first sign in.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[employee.email],
            fail_silently=False,
        )
    except Exception as exc:
        raise self.retry(exc=exc) from exc

    return {"sent": True, "to": employee.email}


@shared_task
def close_stale_login_sessions():
    """Close login-history rows left open by a browser that never logged out.

    Without this, "who is still logged in" slowly fills with people who went
    home three weeks ago.
    """
    cutoff = now_ist().replace(hour=0, minute=0, second=0, microsecond=0)
    closed = (
        LoginHistory.objects.filter(logout_time__isnull=True, login_time__lt=cutoff)
        .update(logout_time=cutoff)
    )
    if closed:
        logger.info("closed %d stale login sessions before %s", closed, today_ist())
    return {"closed": closed}
