"""The service layer base class.

Layering, top to bottom:

    ViewSet      transport. Parses the request, calls one service, renders.
    Serializer   validation and shape. Knows nothing about business rules.
    Service      business rules and transactions. THIS layer.
    Manager      reusable queries.
    Model        persistence.

The rule that keeps it honest: **nothing outside a service writes to the
database.** A view that calls ``Model.objects.create()`` is a bug, because the
next caller — a Celery task, a management command, an import script — will not
get the same rules applied.
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from django.db import transaction

from core.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

logger = logging.getLogger("opstracking.services")

T = TypeVar("T")


class BaseService:
    """Every service takes the acting user in its constructor.

    Passing the actor explicitly — rather than reaching for a thread-local
    "current request" — is what lets the same service run inside a Celery task
    or a management command where no request exists.
    """

    def __init__(self, actor=None):
        self.actor = actor

    # ── guards ───────────────────────────────────────────────

    def require(self, condition: Any, message: str, *, code: str = "forbidden") -> None:
        """Assert a business rule, raising the mapped DomainError.

        ``require`` is truthiness-based on purpose, so the common
        ``self.require(obj, "...")`` after a ``.first()`` reads naturally.
        """
        if not condition:
            raise _ERROR_FOR_CODE.get(code, DomainError)(message, code=code)

    def require_found(self, obj: T | None, message: str = "Not found.") -> T:
        """Return the object or raise 404. Use after ``.first()``.

        This is the fix for "success response on a missing record": the
        service refuses to continue rather than returning a cheerful 200 for
        an update that touched zero rows.
        """
        if obj is None:
            raise NotFoundError(message)
        return obj

    def require_actor(self):
        """Services that mutate data need to know who is acting."""
        if self.actor is None:
            raise PermissionDeniedError("This action requires a signed-in user.")
        return self.actor

    def require_supervisor(self, message: str = "Only a supervisor can do that.") -> None:
        self.require(self.require_actor().is_supervisor, message)

    def require_admin(self, message: str = "Only an administrator can do that.") -> None:
        self.require(self.require_actor().is_admin, message)

    def require_owner_or_supervisor(self, owner_emp_id: str,
                                    message: str = "That record belongs to someone else.") -> None:
        actor = self.require_actor()
        self.require(owner_emp_id == actor.emp_id or actor.is_supervisor, message)

    # ── conveniences ─────────────────────────────────────────

    @property
    def actor_emp_id(self) -> str | None:
        return getattr(self.actor, "emp_id", None)

    @staticmethod
    def atomic():
        """``with self.atomic():`` for services that need a block rather than
        decorating the whole method."""
        return transaction.atomic()

    @staticmethod
    def on_commit(fn) -> None:
        """Defer a side effect until the transaction actually commits.

        Every realtime publish and every Celery ``.delay()`` goes through
        here. Firing before commit lets a subscriber fetch a row that does not
        exist yet — or worse, react to a transaction that then rolls back.
        """
        transaction.on_commit(fn)

    def log(self, event: str, **fields) -> None:
        logger.info(
            "%s.%s actor=%s %s",
            type(self).__name__,
            event,
            self.actor_emp_id or "system",
            " ".join(f"{k}={v}" for k, v in fields.items()),
        )


_ERROR_FOR_CODE = {
    "validation_error": ValidationError,
    "not_found": NotFoundError,
    "forbidden": PermissionDeniedError,
    "conflict": ConflictError,
}
