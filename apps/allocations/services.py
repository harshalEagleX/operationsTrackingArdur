"""Allocation business rules.

Creating and reassigning allocations is a supervisor action — that is the fix
for "an employee can create allocations for themselves".
"""

from __future__ import annotations

from django.db import transaction

from apps.allocations.models import (
    AllocationStatus,
    BatchAllocation,
    OrderHistory,
)
from core.exceptions import ConflictError, ValidationError
from core.services import BaseService
from core.timezone import now_ist


class AllocationService(BaseService):
    """Assign, progress and complete allocations."""

    @transaction.atomic
    def create(self, data: dict) -> BatchAllocation:
        self.require_supervisor("Only a supervisor can allocate work.")

        allocation_id = data.get("allocation_id")
        if allocation_id and BatchAllocation.objects.filter(
            allocation_id=allocation_id
        ).exists():
            raise ConflictError(f"Allocation {allocation_id} already exists.")

        allocation = BatchAllocation.objects.create(
            allocated_by=self.actor_emp_id or "",
            allocated_at=now_ist(),
            **data,
        )

        self._record(allocation, "allocated", to_status=allocation.status)
        self.log("allocation_created", id=allocation.allocation_id)
        self.on_commit(lambda: self._notify_assignee(allocation))
        return allocation

    @transaction.atomic
    def reassign(self, allocation: BatchAllocation, new_employee_id: str,
                 employee_name: str = "") -> BatchAllocation:
        self.require_supervisor("Only a supervisor can reassign work.")

        if allocation.status == AllocationStatus.COMPLETED:
            raise ConflictError("A completed allocation cannot be reassigned.")

        previous = allocation.employee_id
        allocation.employee_id = new_employee_id
        allocation.employee_name = employee_name
        allocation.save(update_fields=["employee_id", "employee_name"])

        self._record(allocation, "reassigned", remarks=f"from {previous} to {new_employee_id}")
        self.log("allocation_reassigned", id=allocation.allocation_id, to=new_employee_id)
        self.on_commit(lambda: self._notify_assignee(allocation))
        return allocation

    @transaction.atomic
    def update_status(self, allocation_pk: int, status: str,
                      completed_quantity: int | None = None,
                      remarks: str = "") -> BatchAllocation:
        allocation = self.require_found(
            BatchAllocation.objects.select_for_update().filter(pk=allocation_pk).first(),
            "No such allocation.",
        )

        # An employee may progress their own work; changing anyone else's is
        # a supervisor action.
        self.require_owner_or_supervisor(
            allocation.employee_id, "That allocation is assigned to someone else."
        )

        if status not in AllocationStatus.values:
            raise ValidationError(f"'{status}' is not a valid status.")

        if allocation.status == AllocationStatus.COMPLETED and not (
            self.actor and self.actor.is_supervisor
        ):
            raise ConflictError("A completed allocation can only be reopened by a supervisor.")

        previous = allocation.status
        allocation.status = status

        if completed_quantity is not None:
            if completed_quantity < 0 or completed_quantity > allocation.quantity:
                raise ValidationError(
                    f"Completed quantity must be between 0 and {allocation.quantity}."
                )
            allocation.completed_quantity = completed_quantity

        if status == AllocationStatus.IN_PROGRESS and not allocation.started_at:
            allocation.started_at = now_ist()
        if status == AllocationStatus.COMPLETED:
            allocation.completed_at = now_ist()

        if remarks:
            allocation.remarks = remarks[:500]

        allocation.save()

        self._record(
            allocation, f"status_{status}", from_status=previous,
            to_status=status, quantity=allocation.completed_quantity, remarks=remarks,
        )
        self.log("allocation_status", id=allocation.allocation_id, status=status)
        self.on_commit(lambda: self._announce(allocation))
        return allocation

    @transaction.atomic
    def cancel(self, allocation: BatchAllocation, reason: str = "") -> BatchAllocation:
        self.require_supervisor("Only a supervisor can cancel an allocation.")

        if allocation.status == AllocationStatus.COMPLETED:
            raise ConflictError("A completed allocation cannot be cancelled.")

        previous = allocation.status
        allocation.status = AllocationStatus.CANCELLED
        allocation.remarks = (reason or allocation.remarks)[:500]
        allocation.save(update_fields=["status", "remarks"])

        self._record(allocation, "cancelled", from_status=previous,
                     to_status=AllocationStatus.CANCELLED, remarks=reason)
        self.on_commit(lambda: self._announce(allocation))
        return allocation

    # ── internals ────────────────────────────────────────────

    def _record(self, allocation: BatchAllocation, action: str, **fields) -> None:
        OrderHistory.objects.create(
            allocation_id=allocation.allocation_id,
            order_id=allocation.order_id,
            employee_id=allocation.employee_id,
            action=action,
            performed_by=self.actor_emp_id or "system",
            created_at=now_ist(),
            **fields,
        )

    @staticmethod
    def _notify_assignee(allocation: BatchAllocation) -> None:
        from apps.notifications.services import NotificationService

        NotificationService().notify(
            recipients=[allocation.employee_id],
            notif_type="allocation.assigned",
            context={
                "task_id": allocation.allocation_id,
                "project": allocation.project,
                "quantity": allocation.quantity,
            },
            link=f"/userdashboard?tab=tasks&allocation={allocation.allocation_id}",
        )

    @staticmethod
    def _announce(allocation: BatchAllocation) -> None:
        from apps.realtime.groups import user_group
        from core.events import publish

        publish(
            group=user_group(allocation.employee_id),
            event="allocation.updated",
            data={
                "id": allocation.id,
                "allocation_id": allocation.allocation_id,
                "status": allocation.status,
                "progress_percent": allocation.progress_percent,
            },
        )
