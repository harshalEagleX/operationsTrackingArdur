"""ASGI middleware that authenticates the WebSocket handshake by ticket.

Runs before SessionMiddlewareStack in asgi.py, so a valid ticket wins and the
session cookie is the fallback. Either way the connection is authenticated
once, at handshake — which is exactly why logout has to explicitly close open
sockets (see apps/accounts/services.py).
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger("opstracking.realtime")


@database_sync_to_async
def _redeem_ticket(token: str):
    from apps.accounts.models import User
    from apps.realtime.tickets import TicketService

    payload = TicketService().redeem(token)
    if not payload:
        return None, None

    user = User.objects.filter(emp_id=payload["emp_id"], status="active").first()
    return user, payload.get("session_key")


class TicketAuthMiddleware(BaseMiddleware):
    """Resolve ``?ticket=`` into ``scope["user"]``."""

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode(errors="ignore"))
        token = (query.get("ticket") or [None])[0]

        if token:
            try:
                user, session_key = await _redeem_ticket(token)
            except Exception:
                logger.exception("ticket redemption failed")
                user, session_key = None, None

            if user is not None:
                scope["user"] = user
                scope["session_key"] = session_key
            else:
                # An invalid ticket must not silently fall through to the
                # session cookie — it is a signal something is wrong, and the
                # consumer should reject rather than guess.
                logger.info("rejected websocket handshake: invalid or expired ticket")
                scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
