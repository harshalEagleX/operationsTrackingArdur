"""Presence background tasks."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache

from apps.presence.models import PresenceState, PresenceStatus
from apps.presence.services import STATE_KEY, PresenceService
from core.timezone import now_ist

logger = logging.getLogger("opstracking.tasks")


@shared_task
def reap_stale_presence():
    """Mark dead sockets offline. Beat, every 30 seconds.

    A force-quit browser, a slammed laptop lid or a train tunnel never fires
    ``disconnect``. The Redis TTL expires the live key; this task reconciles
    the durable table against it, so those users do not stay green forever.
    """
    grace = getattr(settings, "WS_HEARTBEAT_GRACE", 45)
    cutoff = now_ist() - timedelta(seconds=grace)

    stale = PresenceState.objects.filter(last_seen_at__lt=cutoff).exclude(
        status=PresenceStatus.OFFLINE
    )

    service = PresenceService()
    reaped = 0
    for state in stale.iterator():
        # If the Redis key is still alive the user is genuinely connected and
        # the durable row is simply behind — leave them alone.
        if cache.get(STATE_KEY.format(emp_id=state.emp_id)):
            continue
        service.force_offline(state.emp_id)
        reaped += 1

    if reaped:
        logger.info("reaped %d stale presence rows", reaped)
    return {"reaped": reaped}


@shared_task
def refresh_derived_presence():
    """Reconcile presence against breaks and work sessions.

    Presence is normally updated by the service that caused the change. This
    is the safety net for the case where a publish was lost or a row was
    changed outside the service layer (a manual SQL fix, an import).
    """
    from apps.breaks.models import BreakTime
    from apps.tracking.models import WorkSession

    service = PresenceService()
    emp_ids = set(
        BreakTime.objects.open().values_list("user_id", flat=True)
    ) | set(
        WorkSession.objects.active_now().values_list("emp_id", flat=True)
    )

    for emp_id in emp_ids:
        service.recompute(emp_id)

    return {"recomputed": len(emp_ids)}
