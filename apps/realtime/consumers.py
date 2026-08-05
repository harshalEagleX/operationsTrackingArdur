"""The gateway consumer.

One socket per browser tab. It multiplexes presence, notifications and work
events over topic-tagged frames, and will carry chat when that lands — no new
socket required.
"""

from __future__ import annotations

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from apps.realtime.groups import can_subscribe, default_groups_for
from apps.realtime.protocol import (
    ClientOp,
    CloseCode,
    error_frame,
    is_valid_client_frame,
    pong_frame,
    ready_frame,
)

logger = logging.getLogger("opstracking.realtime")

MAX_TOPICS_PER_SOCKET = 50
MAX_REPLAY_EVENTS = 200


class GatewayConsumer(AsyncJsonWebsocketConsumer):
    """Authenticated, multiplexed event gateway."""

    async def connect(self):
        user = self.scope.get("user")

        if not user or not user.is_authenticated or not user.is_active:
            await self.close(code=CloseCode.UNAUTHENTICATED)
            return

        self.user = user
        self.emp_id = user.emp_id
        self.session_key = self.scope.get("session_key")
        self.joined_groups: set[str] = set()

        await self.accept()

        for group in await database_sync_to_async(default_groups_for)(user):
            await self._join(group)

        await self._mark_connected()

        await self.send_json(
            ready_frame(
                emp_id=self.emp_id,
                cursors=await self._topic_cursors(),
                heartbeat_interval=getattr(settings, "WS_HEARTBEAT_INTERVAL", 20),
                groups=sorted(self.joined_groups),
            )
        )

        logger.info("websocket connected: %s (%d topics)", self.emp_id, len(self.joined_groups))

    async def disconnect(self, code):
        if not hasattr(self, "emp_id"):
            return

        for group in list(self.joined_groups):
            await self.channel_layer.group_discard(group, self.channel_name)

        await self._mark_disconnected()
        logger.info("websocket disconnected: %s (code %s)", self.emp_id, code)

    # ── inbound ──────────────────────────────────────────────

    async def receive_json(self, content, **kwargs):
        valid, reason = is_valid_client_frame(content)
        if not valid:
            await self.send_json(error_frame("bad_frame", reason))
            return

        op = content["op"]
        data = content.get("data") or {}

        try:
            handler = {
                ClientOp.PING: self._handle_ping,
                ClientOp.SUB: self._handle_sub,
                ClientOp.UNSUB: self._handle_unsub,
                ClientOp.RESUME: self._handle_resume,
                ClientOp.PRESENCE_SET: self._handle_presence_set,
                ClientOp.TYPING: self._handle_typing,
            }[op]
            await handler(data)
        except Exception:
            logger.exception("error handling op %s from %s", op, self.emp_id)
            await self.send_json(error_frame("server_error", "Could not process that."))

    async def _handle_ping(self, data):
        await self.send_json(pong_frame())
        await self._heartbeat()

    async def _handle_sub(self, data):
        topic = data.get("topic", "")

        if len(self.joined_groups) >= MAX_TOPICS_PER_SOCKET:
            await self.send_json(error_frame("too_many_topics", "Subscription limit reached."))
            return

        # Authorise every join. Without this an authenticated user can
        # subscribe to any topic they can name.
        allowed = await database_sync_to_async(can_subscribe)(self.user, topic)
        if not allowed:
            logger.warning("refused subscription: %s → %s", self.emp_id, topic)
            await self.send_json(error_frame("forbidden", "You cannot subscribe to that topic."))
            return

        await self._join(topic)
        await self.send_json({"v": 1, "op": "ack", "topic": topic, "data": {"subscribed": True}})

    async def _handle_unsub(self, data):
        topic = data.get("topic", "")
        if topic in self.joined_groups:
            await self.channel_layer.group_discard(topic, self.channel_name)
            self.joined_groups.discard(topic)
        await self.send_json({"v": 1, "op": "ack", "topic": topic, "data": {"subscribed": False}})

    async def _handle_resume(self, data):
        """Replay the gap after a reconnect.

        The client sends its last-seen sequence per topic; we send back
        everything since. This is what makes a 30-second tunnel invisible.
        """
        cursors = data.get("cursors") or {}
        if not isinstance(cursors, dict):
            await self.send_json(error_frame("bad_frame", "cursors must be an object."))
            return

        replayed = 0
        for topic, last_seq in list(cursors.items())[:MAX_TOPICS_PER_SOCKET]:
            if topic not in self.joined_groups:
                continue
            for frame in await self._replay(topic, last_seq):
                await self.send_json(frame)
                replayed += 1

        if replayed:
            logger.info("replayed %d events to %s on resume", replayed, self.emp_id)

    async def _handle_presence_set(self, data):
        status = data.get("status")
        if status not in ("online", "busy", "idle"):
            await self.send_json(error_frame("validation_error", "Unsupported status."))
            return
        await self._set_manual_presence(status, data.get("custom_status", ""))

    async def _handle_typing(self, data):
        """Reserved for chat.

        Typing is one of only two things that legitimately travel client→server
        over the socket: it is ephemeral, high-frequency, and never persisted.
        """
        await self.send_json(
            error_frame("not_implemented", "Chat is not enabled on this deployment.")
        )

    # ── outbound (invoked by channel_layer.group_send) ───────

    async def fanout(self, message):
        """Deliver a published event. Named to match core.events.publish."""
        if message.get("exclude") == self.emp_id:
            return
        await self.send_json(message["payload"])

    async def session_revoked(self, message):
        """Close the socket when its session is signed out.

        The client treats 4401 as "go to /login", not "reconnect" — otherwise
        a signed-out tab reconnects forever against an endpoint that will
        never accept it.
        """
        revoked_key = message.get("session_key")
        if revoked_key in (None, "", self.session_key):
            logger.info("closing socket for %s: session revoked", self.emp_id)
            await self.close(code=CloseCode.UNAUTHENTICATED)

    # ── helpers ──────────────────────────────────────────────

    async def _join(self, group: str) -> None:
        await self.channel_layer.group_add(group, self.channel_name)
        self.joined_groups.add(group)

    @database_sync_to_async
    def _topic_cursors(self) -> dict:
        """The newest outbox id per topic this socket is subscribed to, so a
        fresh connection starts from 'now' instead of replaying history."""
        from django.db.models import Max

        from apps.realtime.models import OutboxEvent

        rows = (
            OutboxEvent.objects.filter(topic__in=list(self.joined_groups))
            .values("topic")
            .annotate(latest=Max("id"))
        )
        return {row["topic"]: row["latest"] for row in rows}

    @database_sync_to_async
    def _replay(self, topic: str, last_seq) -> list[dict]:
        from apps.realtime.models import OutboxEvent

        try:
            last_seq = int(last_seq)
        except (TypeError, ValueError):
            return []

        events = OutboxEvent.objects.filter(topic=topic, id__gt=last_seq).order_by("id")[
            :MAX_REPLAY_EVENTS
        ]
        return [event.to_frame() for event in events]

    @database_sync_to_async
    def _mark_connected(self):
        from apps.presence.services import PresenceService

        PresenceService().connect(self.emp_id)

    @database_sync_to_async
    def _mark_disconnected(self):
        from apps.presence.services import PresenceService

        PresenceService().disconnect(self.emp_id)

    @database_sync_to_async
    def _heartbeat(self):
        from apps.presence.services import PresenceService

        PresenceService().heartbeat(self.emp_id)

    @database_sync_to_async
    def _set_manual_presence(self, status: str, custom_status: str):
        from apps.presence.services import PresenceService

        PresenceService().set_manual(self.emp_id, status, custom_status)
