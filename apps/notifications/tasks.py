"""Notification background tasks."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from apps.notifications.models import Notification
from core.timezone import now_ist

logger = logging.getLogger("opstracking.tasks")

READ_RETENTION_DAYS = 60
UNREAD_RETENTION_DAYS = 180


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_notification_emails(self, notification_ids: list[int]):
    """Send the email copy of notifications that ask for one."""
    from apps.accounts.models import Employee

    notifications = list(Notification.objects.filter(id__in=notification_ids))
    if not notifications:
        return {"sent": 0}

    emails = dict(
        Employee.objects.filter(
            employee_id__in={n.recipient_emp_id for n in notifications}
        )
        .exclude(email="")
        .values_list("employee_id", "email")
    )

    sent = 0
    for notification in notifications:
        address = emails.get(notification.recipient_emp_id)
        if not address:
            continue
        try:
            send_mail(
                subject=notification.title,
                message=f"{notification.body}\n\n{notification.link_url}".strip(),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[address],
                fail_silently=False,
            )
            sent += 1
        except Exception as exc:
            logger.warning("email failed for notification %s: %s", notification.id, exc)
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc) from exc

    return {"sent": sent, "requested": len(notification_ids)}


@shared_task
def prune_notifications():
    """Delete old notifications. Beat, nightly at 02:15.

    Read notifications go after 60 days; unread after 180. Keeping unread ones
    longer matters — an employee back from three months of leave should still
    see what they missed.
    """
    read_cutoff = now_ist() - timedelta(days=READ_RETENTION_DAYS)
    unread_cutoff = now_ist() - timedelta(days=UNREAD_RETENTION_DAYS)

    read_deleted, _ = Notification.objects.filter(
        read_at__isnull=False, read_at__lt=read_cutoff
    ).delete()
    unread_deleted, _ = Notification.objects.filter(
        read_at__isnull=True, created_at__lt=unread_cutoff
    ).delete()
    expired_deleted, _ = Notification.objects.filter(
        expires_at__isnull=False, expires_at__lt=now_ist()
    ).delete()

    total = read_deleted + unread_deleted + expired_deleted
    if total:
        logger.info(
            "pruned %d notifications (%d read, %d unread, %d expired)",
            total, read_deleted, unread_deleted, expired_deleted,
        )
    return {"deleted": total}
