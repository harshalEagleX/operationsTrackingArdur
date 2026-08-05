"""Durable presence state.

Live presence lives in Redis with a TTL — it changes constantly and does not
need to survive a restart. This table is the last-known value, so a page load
can render the roster in one query without waiting for every client to send
its next heartbeat.
"""

from __future__ import annotations

from django.db import models

from core.timezone import now_ist


class PresenceStatus(models.TextChoices):
    """Ordered by precedence — see PresenceService.recompute()."""

    ON_BREAK = "on_break", "On break"
    WORKING = "working", "Working"
    BUSY = "busy", "Busy"
    ONLINE = "online", "Online"
    IDLE = "idle", "Idle"
    OFFLINE = "offline", "Offline"


class StatusSource(models.TextChoices):
    SOCKET = "socket", "Socket"
    WORK_SESSION = "work_session", "Work session"
    BREAK = "break", "Break"
    MANUAL = "manual", "Manual"


class PresenceState(models.Model):
    """One row per employee. The emp_id is the primary key — presence is a
    property of a person, not an event stream."""

    emp_id = models.CharField(max_length=20, primary_key=True)
    status = models.CharField(
        max_length=10, choices=PresenceStatus.choices,
        default=PresenceStatus.OFFLINE, db_index=True,
    )
    status_source = models.CharField(
        max_length=15, choices=StatusSource.choices, default=StatusSource.SOCKET
    )
    custom_status = models.CharField(max_length=80, blank=True, default="")
    connection_count = models.SmallIntegerField(default=0)

    last_seen_at = models.DateTimeField(default=now_ist, db_index=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(default=now_ist)

    class Meta:
        db_table = "ot_presence"
        ordering = ["emp_id"]
        indexes = [
            models.Index(fields=["status", "last_seen_at"], name="ix_presence_status"),
        ]

    def __str__(self) -> str:
        return f"{self.emp_id}: {self.status}"

    @property
    def is_online(self) -> bool:
        return self.status != PresenceStatus.OFFLINE
