"""Notification delivery.

One call site — ``NotificationService().notify()``. Every feature that wants
to tell someone something goes through it, which is why turning a type off in
preferences actually turns it off everywhere.

Always call from ``transaction.on_commit``. For large audiences, hand the whole
thing to Celery so the HTTP request returns immediately.
"""

from __future__ import annotations

import logging

from django.db import transaction

from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.registry import get as get_type
from apps.notifications.registry import render_title
from core.events import publish
from core.services import BaseService
from core.timezone import now_ist

logger = logging.getLogger("opstracking.notifications")

BULK_THRESHOLD = 25


class NotificationService(BaseService):
    """Create and deliver notifications."""

    def notify(
        self,
        recipients,
        notif_type: str,
        context: dict | None = None,
        *,
        link: str = "",
        actor=None,
        expires_at=None,
    ) -> list[Notification]:
        context = context or {}
        spec = get_type(notif_type)
        actor = actor or self.actor
        actor_emp_id = getattr(actor, "emp_id", "")

        # Never notify someone about their own action.
        targets = {e for e in recipients if e and e != actor_emp_id}
        if not targets:
            return []

        wanted = self._filter_by_preference(targets, notif_type, "in_app", spec.default_in_app)
        if not wanted:
            return []

        rows = [
            Notification(
                recipient_emp_id=emp_id,
                notif_type=notif_type,
                title=render_title(notif_type, context)[:150],
                body=str(context.get("body", ""))[:500],
                payload=context,
                link_url=link[:255],
                priority=spec.priority,
                actor_emp_id=actor_emp_id,
                created_at=now_ist(),
                expires_at=expires_at,
            )
            for emp_id in sorted(wanted)
        ]

        created = Notification.objects.bulk_create(rows)

        # bulk_create does not populate primary keys on every backend, so
        # re-read when the ids are actually needed for the push payload.
        if created and created[0].pk is None:
            created = list(
                Notification.objects.filter(
                    notif_type=notif_type,
                    recipient_emp_id__in=wanted,
                    created_at__gte=rows[0].created_at,
                ).order_by("-id")[: len(rows)]
            )

        self._deliver(created)

        email_targets = self._filter_by_preference(
            wanted, notif_type, "email", spec.default_email
        )
        if email_targets:
            self._queue_emails([n for n in created if n.recipient_emp_id in email_targets])

        logger.info("notified %d recipient(s) of %s", len(created), notif_type)
        return created

    def mark_read(self, emp_id: str, notification_ids: list[int] | None = None) -> int:
        """Mark some or all of a user's notifications read."""
        query = Notification.objects.filter(recipient_emp_id=emp_id, read_at__isnull=True)
        if notification_ids:
            query = query.filter(id__in=notification_ids)

        count = query.update(read_at=now_ist())

        if count:
            from apps.realtime.groups import user_group

            transaction.on_commit(
                lambda: publish(
                    group=user_group(emp_id),
                    event="notification.read",
                    data={"ids": notification_ids or "all", "unread_count": self.unread_count(emp_id)},
                    durable=False,
                )
            )
        return count

    @staticmethod
    def unread_count(emp_id: str) -> int:
        return Notification.objects.filter(
            recipient_emp_id=emp_id, read_at__isnull=True
        ).count()

    def set_preference(self, emp_id: str, notif_type: str, *, in_app: bool, email: bool):
        spec = get_type(notif_type)
        if not spec.user_configurable:
            from core.exceptions import ValidationError

            raise ValidationError(f"'{notif_type}' notifications cannot be turned off.")

        preference, _ = NotificationPreference.objects.update_or_create(
            emp_id=emp_id,
            notif_type=notif_type,
            defaults={"in_app": in_app, "email": email},
        )
        return preference

    # ── internals ────────────────────────────────────────────

    @staticmethod
    def _filter_by_preference(emp_ids, notif_type: str, channel: str, default: bool) -> set[str]:
        """Resolve preferences for a whole audience in one query.

        Checking per recipient would be an N+1 on the hot path of every
        business action that notifies anyone.
        """
        overrides = dict(
            NotificationPreference.objects.filter(
                emp_id__in=emp_ids, notif_type=notif_type
            ).values_list("emp_id", channel)
        )
        return {emp_id for emp_id in emp_ids if overrides.get(emp_id, default)}

    @staticmethod
    def _deliver(notifications: list[Notification]) -> None:
        """Push each notification to its recipient's socket."""
        from apps.notifications.serializers import NotificationSerializer
        from apps.realtime.groups import user_group

        for notification in notifications:
            publish(
                group=user_group(notification.recipient_emp_id),
                event="notification.created",
                data=NotificationSerializer(notification).data,
            )

    @staticmethod
    def _queue_emails(notifications: list[Notification]) -> None:
        if not notifications:
            return
        from apps.notifications.tasks import send_notification_emails

        ids = [n.id for n in notifications if n.id]
        if ids:
            transaction.on_commit(lambda: send_notification_emails.delay(ids))
