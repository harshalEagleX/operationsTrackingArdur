"""The durable event outbox.

Redis pub/sub is fire-and-forget: if a socket is down for eight seconds, those
events are gone. The outbox is the log that makes the realtime layer *correct*
rather than merely fast.

On reconnect the client sends its last-seen id per topic and the server
replays the gap. Pruned nightly — seven days is far more than any reconnect
needs and keeps the table small.
"""

from __future__ import annotations

from django.db import models

from core.timezone import now_ist


class OutboxEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    topic = models.CharField(max_length=80, db_index=True)
    audience = models.CharField(max_length=80)
    event_type = models.CharField(max_length=60)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=now_ist, db_index=True)

    class Meta:
        db_table = "ot_realtime_outbox"
        ordering = ["id"]
        indexes = [
            # The replay query: WHERE topic = ? AND id > ? ORDER BY id
            models.Index(fields=["topic", "id"], name="ix_outbox_topic_id"),
        ]

    def __str__(self) -> str:
        return f"[{self.id}] {self.event_type} → {self.topic}"

    def to_frame(self) -> dict:
        from apps.realtime.protocol import ServerOp, envelope

        return envelope(
            ServerOp.EVENT,
            topic=self.topic,
            event_type=self.event_type,
            data=self.payload,
            seq=self.id,
        )


class WebSocketTicket(models.Model):
    """Fallback ticket store for when the cache backend is not shared.

    Tickets normally live in Redis (see tickets.py) because they expire in
    60 seconds and a database row for each is wasteful. This model exists so
    the ticket flow still works in tests and in a single-process deployment
    with a local-memory cache.
    """

    token = models.CharField(max_length=64, primary_key=True)
    emp_id = models.CharField(max_length=20, db_index=True)
    session_key = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(default=now_ist)
    expires_at = models.DateTimeField(db_index=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ot_ws_tickets"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"ticket for {self.emp_id} (expires {self.expires_at:%H:%M:%S})"

    @property
    def is_usable(self) -> bool:
        return self.redeemed_at is None and self.expires_at > now_ist()
