"""Short-lived, single-use WebSocket handshake tickets.

The session cookie is sent on a same-origin WebSocket handshake, so session
auth usually works on its own. The ticket is the robust path: it survives
proxy quirks, cookie-partitioning changes, and any future move to a separate
subdomain.

Single-use with a 60-second TTL, so even if a ticket leaks into a proxy access
log it is worthless by the time anyone reads it.
"""

from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.core.cache import cache

from core.timezone import now_ist

logger = logging.getLogger("opstracking.realtime")

TICKET_PREFIX = "wsticket:"


class TicketService:
    """Issue and redeem handshake tickets."""

    @property
    def ttl(self) -> int:
        return getattr(settings, "WS_TICKET_TTL", 60)

    def issue(self, user, session_key: str | None = None) -> dict:
        token = secrets.token_urlsafe(32)
        payload = {
            "emp_id": user.emp_id,
            "session_key": session_key or "",
            "issued_at": now_ist().isoformat(),
        }

        cache.set(TICKET_PREFIX + token, payload, timeout=self.ttl)
        self._mirror_to_db(token, payload)

        return {"ticket": token, "expires_in": self.ttl}

    def redeem(self, token: str) -> dict | None:
        """Consume a ticket. Returns its payload, or None if it is invalid.

        Deleted on read — a replayed ticket is dead.
        """
        if not token:
            return None

        key = TICKET_PREFIX + token
        payload = cache.get(key)

        if payload is not None:
            cache.delete(key)
            # The cache is the fast path, but the DB mirror exists so a
            # different process (Daphne vs Gunicorn on a local-memory cache)
            # can still redeem this ticket — and that means it must be
            # marked redeemed here too, or that other process's fallback
            # query still sees redeemed_at IS NULL and hands the same
            # ticket out a second time.
            self._mark_redeemed_in_db(token)
            return payload

        return self._redeem_from_db(token)

    # ── database mirror ──────────────────────────────────────
    # Redis is authoritative. The mirror keeps the flow working with a
    # local-memory cache, where each process has its own cache and the
    # Daphne process would otherwise never see a ticket issued by Gunicorn.

    def _mirror_to_db(self, token: str, payload: dict) -> None:
        from datetime import timedelta

        from apps.realtime.models import WebSocketTicket

        try:
            WebSocketTicket.objects.create(
                token=token,
                emp_id=payload["emp_id"],
                session_key=payload["session_key"],
                expires_at=now_ist() + timedelta(seconds=self.ttl),
            )
        except Exception:
            logger.warning("could not mirror ws ticket to database", exc_info=True)

    def _mark_redeemed_in_db(self, token: str) -> None:
        from apps.realtime.models import WebSocketTicket

        try:
            WebSocketTicket.objects.filter(token=token, redeemed_at__isnull=True).update(
                redeemed_at=now_ist()
            )
        except Exception:
            logger.warning("could not mark ws ticket redeemed in database mirror", exc_info=True)

    def _redeem_from_db(self, token: str) -> dict | None:
        from apps.realtime.models import WebSocketTicket

        try:
            ticket = WebSocketTicket.objects.filter(token=token).first()
            if ticket is None or not ticket.is_usable:
                return None

            # Mark redeemed under a conditional update so two concurrent
            # handshakes cannot both claim the same ticket.
            claimed = WebSocketTicket.objects.filter(
                token=token, redeemed_at__isnull=True
            ).update(redeemed_at=now_ist())
            if not claimed:
                return None

            return {"emp_id": ticket.emp_id, "session_key": ticket.session_key}
        except Exception:
            logger.warning("could not redeem ws ticket from database", exc_info=True)
            return None


def purge_expired_tickets() -> int:
    """Housekeeping for the database mirror. Redis expires its own keys."""
    from apps.realtime.models import WebSocketTicket

    deleted, _ = WebSocketTicket.objects.filter(expires_at__lt=now_ist()).delete()
    return deleted
