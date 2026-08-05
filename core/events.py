"""The single realtime publish entry point.

Nothing in this codebase calls ``channel_layer`` directly except this module.
One function means one place to write the durable outbox row, one place to
instrument, and one place to change transport if this ever stops being
Channels.

Always call it from ``transaction.on_commit()``. Publishing mid-transaction
lets a subscriber fetch a row that has not committed yet — or react to one
that then rolls back.
"""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from core.timezone import now_ist

logger = logging.getLogger("opstracking.events")

PROTOCOL_VERSION = 1


def publish(
    *,
    group: str,
    event: str,
    data: dict,
    durable: bool = True,
    exclude: str | None = None,
) -> int | None:
    """Fan an event out to a Channels group.

    Args:
        group:   the channel group / topic, e.g. "user.E1042".
        event:   dotted event type, e.g. "work.session.completed".
        data:    JSON-serialisable payload.
        durable: write an outbox row first so a client that was offline can
                 replay it on reconnect. Set False for ephemeral signals
                 (typing, read receipts) where replay has no value.
        exclude: emp_id to skip — normally the actor, who already knows.

    Returns:
        The outbox sequence id when durable, else None. The client uses it as
        its per-topic replay cursor.
    """
    seq = None

    if durable:
        # Imported lazily: core must not import from apps at module scope.
        from apps.realtime.models import OutboxEvent

        seq = OutboxEvent.objects.create(
            topic=group,
            audience=group,
            event_type=event,
            payload=data,
        ).id

    envelope = {
        "v": PROTOCOL_VERSION,
        "op": "event",
        "topic": group,
        "type": event,
        "seq": seq,
        "ts": now_ist().isoformat(),
        "data": data,
    }

    layer = get_channel_layer()
    if layer is None:  # pragma: no cover — only when CHANNEL_LAYERS is unset
        logger.warning("no channel layer configured; dropped %s -> %s", event, group)
        return seq

    try:
        async_to_sync(layer.group_send)(
            group, {"type": "fanout", "exclude": exclude, "payload": envelope}
        )
    except Exception:
        # A realtime push is a nice-to-have. Redis being down must never turn
        # a successful business write into a 500 — the outbox row is already
        # committed, so the client will pick it up on its next sync.
        logger.exception("publish failed for %s -> %s", event, group)

    return seq


def publish_to_user(emp_id: str, event: str, data: dict, *, durable: bool = True) -> int | None:
    from apps.realtime.groups import user_group

    return publish(group=user_group(emp_id), event=event, data=data, durable=durable)


def publish_to_many(emp_ids, event: str, data: dict, *, durable: bool = True) -> None:
    """Fan out to a set of users. Deduplicates — a supervisor who is also the
    assignee should get one notification, not two."""
    for emp_id in {e for e in emp_ids if e}:
        publish_to_user(emp_id, event, data, durable=durable)
