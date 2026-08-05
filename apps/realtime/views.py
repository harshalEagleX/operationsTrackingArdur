"""Realtime HTTP endpoints: ticket issue and the polling fallback."""

from __future__ import annotations

from django.conf import settings
from rest_framework.views import APIView

from apps.realtime.groups import can_subscribe, default_groups_for
from apps.realtime.models import OutboxEvent
from apps.realtime.tickets import TicketService
from core.mixins import EnvelopeMixin
from core.permissions import IsAuthenticatedEmployee

MAX_SYNC_EVENTS = 200


class TicketView(EnvelopeMixin, APIView):
    """POST /api/v1/realtime/ticket/

    The client calls this immediately before opening the socket. Tickets are
    single-use and expire in 60 seconds.
    """

    permission_classes = [IsAuthenticatedEmployee]

    def post(self, request):
        payload = TicketService().issue(request.user, request.session.session_key)
        payload["ws_url"] = self._websocket_url(request)
        return self.ok(payload)

    @staticmethod
    def _websocket_url(request) -> str:
        configured = getattr(settings, "WS_PUBLIC_URL", "")
        if configured:
            return configured.rstrip("/") + "/ws/gateway/"

        scheme = "wss" if request.is_secure() else "ws"
        return f"{scheme}://{request.get_host()}/ws/gateway/"


class SyncView(EnvelopeMixin, APIView):
    """GET /api/v1/realtime/sync/?cursors={"user.E1042":8830}

    Catch-up over HTTP. Two uses:

      * a client that reconnects and would rather batch its replay than
        stream it over the fresh socket;
      * the degraded polling transport, if this ever has to run somewhere
        WebSockets are unavailable.

    Either way the outbox is the same source of truth, so the two transports
    cannot disagree.
    """

    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request):
        import json

        raw = request.query_params.get("cursors", "{}")
        try:
            cursors = json.loads(raw)
            if not isinstance(cursors, dict):
                raise ValueError
        except (ValueError, TypeError):
            from core.exceptions import ValidationError

            raise ValidationError("cursors must be a JSON object of topic → last seq.") from None

        allowed_topics = set(default_groups_for(request.user))
        events, new_cursors = [], {}

        for topic, last_seq in list(cursors.items())[:50]:
            if topic not in allowed_topics and not can_subscribe(request.user, topic):
                continue

            try:
                last_seq = int(last_seq)
            except (TypeError, ValueError):
                continue

            rows = OutboxEvent.objects.filter(topic=topic, id__gt=last_seq).order_by("id")[
                : MAX_SYNC_EVENTS
            ]
            for row in rows:
                events.append(row.to_frame())
                new_cursors[topic] = row.id

        return self.ok(
            {"events": events, "cursors": new_cursors},
            meta={"count": len(events), "next_poll_ms": 4000},
        )
