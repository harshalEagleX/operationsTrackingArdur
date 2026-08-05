"""Break business rules.

Two things this file exists to guarantee:

  * The allowance comes from BREAK_ALLOWANCES, not from the request.
  * A person can have exactly one break open at a time, enforced with a row
    lock and a database constraint rather than a read-then-write check.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction

from apps.breaks.constants import (
    OVERRUN_GRACE_SECONDS,
    allowance_for,
    is_repeatable,
)
from apps.breaks.models import BreakTime
from core.events import publish
from core.exceptions import ConflictError, ValidationError
from core.services import BaseService
from core.timezone import elapsed_seconds, now_ist


class BreakService(BaseService):
    """Start and end breaks."""

    @transaction.atomic
    def start_break(self, break_type: str) -> BreakTime:
        actor = self.require_actor()

        allowance = allowance_for(break_type)
        if allowance is None:
            raise ValidationError(
                f"'{break_type}' is not a recognised break type.", code="validation_error"
            )

        # The row lock is the arbiter. Without it two requests both read "no
        # open break" and both insert — this is a race, and only the database
        # can settle it.
        already_open = (
            BreakTime.objects.select_for_update()
            .filter(user_id=actor.emp_id, end_time__isnull=True)
            .exists()
        )
        if already_open:
            raise ConflictError("You already have a break running. End it before starting another.")

        if not is_repeatable(break_type):
            taken_today = (
                BreakTime.objects.filter(user_id=actor.emp_id, break_type=break_type)
                .for_day()
                .exists()
            )
            if taken_today:
                raise ConflictError(f"You have already taken your {break_type} today.")

        try:
            brk = BreakTime.objects.create(
                user_id=actor.emp_id,
                user_name=actor.display_name,
                break_type=break_type,
                start_time=now_ist(),
                allotted_time=allowance,  # server-owned
            )
        except IntegrityError as exc:
            # The unique partial index caught a race the lock did not, because
            # the two transactions started before either inserted.
            raise ConflictError("You already have a break running.") from exc

        self.log("break_started", type=break_type, allowance=allowance)
        self.on_commit(lambda: self._announce_start(brk))
        return brk

    @transaction.atomic
    def end_break(self, break_id: int | None = None) -> BreakTime:
        """End the caller's open break.

        ``break_id`` is optional: the common case is "end whatever I have
        open", and making the client track the id it just created is a source
        of bugs when a tab is reloaded mid-break.
        """
        actor = self.require_actor()

        query = BreakTime.objects.select_for_update().filter(
            user_id=actor.emp_id, end_time__isnull=True
        )
        if break_id is not None:
            query = query.filter(pk=break_id)

        brk = self.require_found(query.first(), "You do not have a break running.")

        end = now_ist()
        total = elapsed_seconds(brk.start_time, end)

        brk.end_time = end
        brk.total_time = round(total, 2)
        brk.is_overrun = total > (brk.allotted_time or 0) + OVERRUN_GRACE_SECONDS
        brk.save(update_fields=["end_time", "total_time", "is_overrun"])

        self.log("break_ended", id=brk.id, total=brk.total_time, overrun=brk.is_overrun)
        self.on_commit(lambda: self._announce_end(brk))
        return brk

    @transaction.atomic
    def force_end_break(self, break_id: int) -> BreakTime:
        """Supervisor closes someone else's forgotten break."""
        self.require_supervisor("Only a supervisor can end another employee's break.")

        brk = self.require_found(
            BreakTime.objects.select_for_update()
            .filter(pk=break_id, end_time__isnull=True)
            .first(),
            "That break is not running.",
        )

        end = now_ist()
        total = elapsed_seconds(brk.start_time, end)
        brk.end_time = end
        brk.total_time = round(total, 2)
        brk.is_overrun = total > (brk.allotted_time or 0) + OVERRUN_GRACE_SECONDS
        brk.save(update_fields=["end_time", "total_time", "is_overrun"])

        self.log("break_force_ended", id=brk.id, emp_id=brk.user_id)
        self.on_commit(lambda: self._announce_end(brk))
        return brk

    def current_break(self, emp_id: str | None = None) -> BreakTime | None:
        emp_id = emp_id or self.actor_emp_id
        return BreakTime.objects.filter(user_id=emp_id, end_time__isnull=True).first()

    # ── internals ────────────────────────────────────────────

    @staticmethod
    def _announce_start(brk: BreakTime) -> None:
        from apps.presence.services import PresenceService
        from apps.realtime.groups import user_group

        PresenceService().set_status(brk.user_id, "on_break", source="break")
        publish(
            group=user_group(brk.user_id),
            event="break.started",
            data={
                "id": brk.id,
                "break_type": brk.break_type,
                "start_time": brk.start_time.isoformat(),
                "allotted_time": brk.allotted_time,
            },
        )

    @staticmethod
    def _announce_end(brk: BreakTime) -> None:
        from apps.presence.services import PresenceService
        from apps.realtime.groups import user_group

        # Recompute rather than assume "online": the employee may have had a
        # work session running underneath the break.
        PresenceService().recompute(brk.user_id)
        publish(
            group=user_group(brk.user_id),
            event="break.ended",
            data={
                "id": brk.id,
                "break_type": brk.break_type,
                "total_time": brk.total_time,
                "is_overrun": brk.is_overrun,
            },
        )
