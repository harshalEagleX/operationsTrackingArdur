"""Realtime housekeeping."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings

from apps.realtime.models import OutboxEvent
from core.timezone import now_ist

logger = logging.getLogger("opstracking.tasks")


@shared_task
def prune_outbox():
    """Delete outbox rows past the retention window. Beat, nightly at 02:00.

    Seven days is far longer than any reconnect needs. Without pruning this is
    the fastest-growing table in the schema.
    """
    days = getattr(settings, "OUTBOX_RETENTION_DAYS", 7)
    cutoff = now_ist() - timedelta(days=days)

    deleted, _ = OutboxEvent.objects.filter(created_at__lt=cutoff).delete()
    if deleted:
        logger.info("pruned %d outbox events older than %d days", deleted, days)
    return {"deleted": deleted}


@shared_task
def purge_websocket_tickets():
    """Clear the expired database mirror of handshake tickets."""
    from apps.realtime.tickets import purge_expired_tickets

    deleted = purge_expired_tickets()
    if deleted:
        logger.debug("purged %d expired websocket tickets", deleted)
    return {"deleted": deleted}
