"""Notification models."""

from __future__ import annotations

from django.db import models

from core.timezone import now_ist


class Notification(models.Model):
    id = models.BigAutoField(primary_key=True)
    recipient_emp_id = models.CharField(max_length=20, db_index=True)
    notif_type = models.CharField(max_length=60, db_index=True)

    title = models.CharField(max_length=150)
    body = models.CharField(max_length=500, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    link_url = models.CharField(max_length=255, blank=True, default="")

    priority = models.CharField(max_length=10, default="normal")
    actor_emp_id = models.CharField(max_length=20, blank=True, default="")

    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=now_ist, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "ot_notifications"
        ordering = ["-id"]
        indexes = [
            # The inbox query: WHERE recipient = ? AND read_at IS NULL ORDER BY id DESC
            models.Index(
                fields=["recipient_emp_id", "read_at", "-id"], name="ix_notif_inbox"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.notif_type} → {self.recipient_emp_id}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None


class NotificationPreference(models.Model):
    """Per-user, per-type delivery choices.

    Absence of a row means "use the registry default" — writing a row for
    every user x every type at signup would be thousands of rows expressing
    nothing.
    """

    id = models.BigAutoField(primary_key=True)
    emp_id = models.CharField(max_length=20, db_index=True)
    notif_type = models.CharField(max_length=60)
    in_app = models.BooleanField(default=True)
    email = models.BooleanField(default=False)

    class Meta:
        db_table = "ot_notification_prefs"
        constraints = [
            models.UniqueConstraint(fields=["emp_id", "notif_type"], name="uq_notif_pref")
        ]

    def __str__(self) -> str:
        return f"{self.emp_id} · {self.notif_type}"
