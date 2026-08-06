"""Celery tasks: thumbnails, orphan cleanup, notification emails, and the
nightly outbox/ticket/notification pruning. Run eagerly under test settings.
"""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.timezone import now_ist

pytestmark = pytest.mark.django_db


def _png_upload(name="photo.png") -> SimpleUploadedFile:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="blue").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


# ── apps.files.tasks ──────────────────────────────────────────

def test_make_thumbnail_generates_a_webp_file(employee):
    from apps.files.models import StoredFile
    from apps.files.services import FileService
    from apps.files.tasks import make_thumbnail

    stored = FileService(actor=employee).store(_png_upload())

    result = make_thumbnail(stored.id)

    assert result["ok"] is True
    stored.refresh_from_db()
    assert stored.thumb_path
    assert stored.absolute_thumb_path.exists()


def test_make_thumbnail_skips_a_non_image_file(employee):
    from apps.files.models import StoredFile
    from apps.files.tasks import make_thumbnail

    stored = StoredFile.objects.create(
        owner_emp_id=employee.emp_id, original_name="doc.pdf",
        stored_path="uploads/misc/doc.pdf", mime_type="application/pdf",
        size_bytes=10, sha256="x" * 64,
    )
    result = make_thumbnail(stored.id)
    assert result == {"ok": False, "reason": "not an image"}


def test_make_thumbnail_handles_a_missing_file_record():
    from apps.files.tasks import make_thumbnail

    result = make_thumbnail(999999)
    assert result["ok"] is False


def test_collect_orphaned_uploads_removes_old_unclaimed_files(employee):
    from apps.files.models import StoredFile
    from apps.files.services import FileService
    from apps.files.tasks import collect_orphaned_uploads

    stored = FileService(actor=employee).store(_png_upload())
    StoredFile.objects.filter(pk=stored.pk).update(
        created_at=now_ist() - timedelta(hours=48)
    )

    result = collect_orphaned_uploads(older_than_hours=24)

    assert result["removed"] == 1
    assert not StoredFile.objects.filter(pk=stored.pk).exists()


def test_collect_orphaned_uploads_leaves_claimed_files_alone(employee):
    from apps.files.models import StoredFile
    from apps.files.services import FileService
    from apps.files.tasks import collect_orphaned_uploads

    stored = FileService(actor=employee).store(_png_upload())
    FileService(actor=employee).claim([stored.id], context="feedback")
    StoredFile.objects.filter(pk=stored.pk).update(created_at=now_ist() - timedelta(hours=48))

    result = collect_orphaned_uploads(older_than_hours=24)

    assert result["removed"] == 0
    assert StoredFile.objects.filter(pk=stored.pk).exists()


def test_collect_orphaned_uploads_leaves_recent_files_alone(employee):
    from apps.files.services import FileService
    from apps.files.tasks import collect_orphaned_uploads

    FileService(actor=employee).store(_png_upload())  # just created, not yet 24h old

    result = collect_orphaned_uploads(older_than_hours=24)
    assert result["removed"] == 0


def test_scan_file_is_an_inert_stub():
    from apps.files.tasks import scan_file

    result = scan_file(1)
    assert result == {"ok": True, "scanned": False, "reason": "no scanner configured"}


# ── apps.notifications.tasks ──────────────────────────────────

def test_send_notification_emails_delivers_to_employees_with_an_address(employee, mailoutbox):
    from apps.accounts.models import Employee
    from apps.notifications.services import NotificationService
    from apps.notifications.tasks import send_notification_emails

    Employee.objects.filter(employee_id=employee.emp_id).update(email="worker@example.com")
    [notification] = NotificationService().notify(
        recipients=[employee.emp_id], notif_type="report.ready", context={"body": "Ready"},
    )

    result = send_notification_emails([notification.id])

    assert result["sent"] == 1
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["worker@example.com"]


def test_send_notification_emails_skips_employees_with_no_address(employee, mailoutbox):
    from apps.notifications.services import NotificationService
    from apps.notifications.tasks import send_notification_emails

    [notification] = NotificationService().notify(
        recipients=[employee.emp_id], notif_type="report.ready", context={},
    )

    result = send_notification_emails([notification.id])

    assert result["sent"] == 0
    assert len(mailoutbox) == 0


def test_send_notification_emails_with_no_matching_ids():
    from apps.notifications.tasks import send_notification_emails

    assert send_notification_emails([999999]) == {"sent": 0}


def test_prune_notifications_removes_old_read_ones(employee):
    from apps.notifications.models import Notification
    from apps.notifications.tasks import prune_notifications

    old_read = Notification.objects.create(
        recipient_emp_id=employee.emp_id, notif_type="report.ready", title="Old",
        read_at=now_ist() - timedelta(days=61), created_at=now_ist() - timedelta(days=61),
    )
    recent_read = Notification.objects.create(
        recipient_emp_id=employee.emp_id, notif_type="report.ready", title="Recent",
        read_at=now_ist(), created_at=now_ist(),
    )

    result = prune_notifications()

    assert result["deleted"] >= 1
    assert not Notification.objects.filter(pk=old_read.pk).exists()
    assert Notification.objects.filter(pk=recent_read.pk).exists()


def test_prune_notifications_removes_old_unread_ones_but_not_recent(employee):
    from apps.notifications.models import Notification
    from apps.notifications.tasks import prune_notifications

    old_unread = Notification.objects.create(
        recipient_emp_id=employee.emp_id, notif_type="report.ready", title="Old unread",
        created_at=now_ist() - timedelta(days=181),
    )
    recent_unread = Notification.objects.create(
        recipient_emp_id=employee.emp_id, notif_type="report.ready", title="Recent unread",
        created_at=now_ist(),
    )

    prune_notifications()

    assert not Notification.objects.filter(pk=old_unread.pk).exists()
    assert Notification.objects.filter(pk=recent_unread.pk).exists()


def test_prune_notifications_removes_expired_ones(employee):
    from apps.notifications.models import Notification
    from apps.notifications.tasks import prune_notifications

    expired = Notification.objects.create(
        recipient_emp_id=employee.emp_id, notif_type="report.ready", title="Expired",
        expires_at=now_ist() - timedelta(minutes=1),
    )

    prune_notifications()
    assert not Notification.objects.filter(pk=expired.pk).exists()


# ── apps.realtime.tasks ───────────────────────────────────────

def test_prune_outbox_removes_events_past_retention():
    from apps.realtime.models import OutboxEvent
    from apps.realtime.tasks import prune_outbox

    old = OutboxEvent.objects.create(
        topic="user.E1", audience="user.E1", event_type="x", payload={},
        created_at=now_ist() - timedelta(days=8),
    )
    recent = OutboxEvent.objects.create(
        topic="user.E1", audience="user.E1", event_type="x", payload={},
        created_at=now_ist(),
    )

    result = prune_outbox()

    assert result["deleted"] >= 1
    assert not OutboxEvent.objects.filter(pk=old.pk).exists()
    assert OutboxEvent.objects.filter(pk=recent.pk).exists()


def test_purge_websocket_tickets_task():
    from apps.realtime.models import WebSocketTicket
    from apps.realtime.tasks import purge_websocket_tickets

    WebSocketTicket.objects.create(
        token="stale", emp_id="E1", expires_at=now_ist() - timedelta(seconds=1)
    )

    result = purge_websocket_tickets()
    assert result["deleted"] == 1
