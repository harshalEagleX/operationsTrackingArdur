"""Signal handlers for tracking.

Deliberately thin. Business rules belong in WorkSessionService, where they run
for every caller — a signal fires only on an ORM save, so an ``.update()`` or
a bulk operation would skip it. These handlers do presence bookkeeping only.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.tracking.models import WorkSession

logger = logging.getLogger("opstracking.tracking")


@receiver(post_delete, sender=WorkSession, dispatch_uid="tracking_session_deleted")
def recompute_presence_on_delete(sender, instance: WorkSession, **kwargs):
    """If someone's only open session is deleted, they are no longer 'working'.

    Presence is derived state — deleting the row it was derived from has to
    trigger a recompute, or the dot stays green until the next heartbeat.
    """
    try:
        from apps.presence.services import PresenceService

        PresenceService().recompute(instance.emp_id)
    except Exception:
        # Presence is cosmetic. It must never turn a successful delete into
        # a 500.
        logger.exception("presence recompute failed after session delete")
