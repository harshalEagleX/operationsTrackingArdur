"""Feedback business rules.

The access rule is the important one: an employee may read feedback about
themselves and feedback they wrote, and nothing else. That is enforced on the
queryset (for lists) and on the object (for detail) — both, because either
alone leaks.
"""

from __future__ import annotations

from django.db import transaction

from apps.feedback.models import Feedback, FeedbackImage
from core.exceptions import ConflictError, ValidationError
from core.services import BaseService
from core.timezone import now_ist


class FeedbackService(BaseService):
    """Create, acknowledge and respond to feedback."""

    @transaction.atomic
    def create(self, data: dict, file_ids: list[int] | None = None) -> Feedback:
        self.require_supervisor("Only a supervisor can record feedback.")
        actor = self.require_actor()

        emp_id = data["emp_id"]
        if emp_id == actor.emp_id:
            raise ValidationError("You cannot record feedback about yourself.")

        error_count = data.get("error_count", 0)
        sample_size = data.get("sample_size", 0)
        if sample_size and error_count > sample_size:
            raise ValidationError("The error count cannot exceed the sample size.")

        feedback = Feedback.objects.create(
            created_by=actor.emp_id,
            created_by_name=actor.display_name,
            created_at=now_ist(),
            **data,
        )

        if file_ids:
            self._attach_files(feedback, file_ids)

        self.log("feedback_created", id=feedback.id, about=emp_id)
        self.on_commit(lambda: self._notify(feedback))
        return feedback

    @transaction.atomic
    def acknowledge(self, feedback_id: int, response: str = "") -> Feedback:
        """The subject confirms they have read it."""
        feedback = self.require_found(
            Feedback.objects.select_for_update().filter(pk=feedback_id).first(),
            "No such feedback.",
        )
        actor = self.require_actor()

        self.require(
            feedback.emp_id == actor.emp_id,
            "Only the employee the feedback is about can acknowledge it.",
        )

        if feedback.is_acknowledged:
            raise ConflictError("You have already acknowledged this feedback.")

        feedback.acknowledged_at = now_ist()
        feedback.response = (response or "")[:2000]
        feedback.save(update_fields=["acknowledged_at", "response"])

        self.log("feedback_acknowledged", id=feedback.id)
        self.on_commit(lambda: self._notify_author(feedback))
        return feedback

    @transaction.atomic
    def update(self, feedback: Feedback, data: dict) -> Feedback:
        """Only the author may edit, and only before it is acknowledged —
        once someone has responded to it, changing the text underneath them
        makes the record dishonest."""
        actor = self.require_actor()
        self.require(
            feedback.created_by == actor.emp_id or actor.is_admin,
            "Only the author can edit this feedback.",
        )
        if feedback.is_acknowledged and not actor.is_admin:
            raise ConflictError("This feedback has been acknowledged and can no longer be edited.")

        data.pop("emp_id", None)  # never move feedback to a different person
        for field, value in data.items():
            setattr(feedback, field, value)
        feedback.save()

        self.log("feedback_updated", id=feedback.id)
        return feedback

    @transaction.atomic
    def delete(self, feedback: Feedback) -> None:
        self.require_admin("Only an administrator can delete feedback.")
        feedback_id = feedback.id
        feedback.delete()
        self.log("feedback_deleted", id=feedback_id)

    def can_read(self, feedback: Feedback) -> bool:
        """The object-level rule, also reused by the file download policy."""
        actor = self.actor
        if actor is None:
            return False
        return (
            actor.is_supervisor
            or feedback.emp_id == actor.emp_id
            or feedback.created_by == actor.emp_id
        )

    # ── internals ────────────────────────────────────────────

    def _attach_files(self, feedback: Feedback, file_ids: list[int]) -> None:
        from apps.files.services import FileService

        files = FileService(self.actor).claim(file_ids, context="feedback")
        FeedbackImage.objects.bulk_create(
            [FeedbackImage(feedback=feedback, file=f, created_at=now_ist()) for f in files]
        )

    @staticmethod
    def _notify(feedback: Feedback) -> None:
        from apps.notifications.services import NotificationService

        NotificationService().notify(
            recipients=[feedback.emp_id],
            notif_type="feedback.received",
            context={
                "order_batch_id": feedback.order_batch_id or feedback.project or "your work",
                "severity": feedback.severity,
                "body": feedback.subject,
            },
            link=f"/userdashboard?tab=feedback&id={feedback.id}",
        )

    @staticmethod
    def _notify_author(feedback: Feedback) -> None:
        from apps.realtime.groups import user_group
        from core.events import publish

        if not feedback.created_by:
            return
        publish(
            group=user_group(feedback.created_by),
            event="feedback.acknowledged",
            data={"id": feedback.id, "emp_id": feedback.emp_id},
        )
