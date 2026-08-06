"""Master data services.

Two responsibilities beyond plain CRUD:

  * Cache invalidation. Any write bumps the ``masters`` cache namespace, so a
    stale dropdown can never outlive the change that caused it.
  * Referential safety. Master rows are referenced by string, not by foreign
    key (that is how the legacy schema works), so the database will not stop
    you deleting a project that 40,000 work sessions point at. The service
    does.
"""

from __future__ import annotations

from django.db import transaction

from apps.masters.models import ClientCode, Project, Shift, WorkType
from core.cache import cached, invalidate_masters
from core.exceptions import ConflictError
from core.services import BaseService
from core.timezone import now_ist


class MasterDataService(BaseService):
    """Shared behaviour for all four master tables.

    Subclasses set ``model`` and ``label``; a ViewSet picks the right one via
    ``for_model()``.
    """

    model = None
    label = "record"
    # (model, field) pairs to check before allowing a delete.
    references: tuple = ()

    @classmethod
    def for_model(cls, model):
        return {
            WorkType: WorkTypeService,
            Project: ProjectService,
            ClientCode: ClientCodeService,
            Shift: ShiftService,
        }[model]

    @transaction.atomic
    def create(self, data: dict):
        self.require_admin(f"Only an administrator can add a {self.label}.")
        instance = self.model.objects.create(
            created_by=self.actor_emp_id or "", **data
        )
        self.on_commit(invalidate_masters)
        self.log("created", model=self.model.__name__, id=instance.pk)
        return instance

    @transaction.atomic
    def update(self, instance, data: dict):
        self.require_admin(f"Only an administrator can change a {self.label}.")
        for field, value in data.items():
            setattr(instance, field, value)
        instance.updated_at = now_ist()
        instance.save()
        self.on_commit(invalidate_masters)
        self.log("updated", model=self.model.__name__, id=instance.pk)
        return instance

    @transaction.atomic
    def deactivate(self, instance):
        """DELETE deactivates rather than removes.

        A project that disappears takes its name out of every historical work
        session's join, and last quarter's report changes shape.
        """
        self.require_admin(f"Only an administrator can remove a {self.label}.")

        in_use = self._usage_count(instance)
        if in_use:
            # Deactivating is still allowed — it just stops new work being
            # booked against it. Hard delete is what we refuse.
            self.log("deactivated_in_use", model=self.model.__name__, rows=in_use)

        instance.is_active = False
        instance.updated_at = now_ist()
        instance.save(update_fields=["is_active", "updated_at"])
        self.on_commit(invalidate_masters)
        return instance

    @transaction.atomic
    def hard_delete(self, instance):
        """Actually remove the row. Refused if anything references it."""
        self.require_admin(f"Only an administrator can delete a {self.label}.")

        in_use = self._usage_count(instance)
        if in_use:
            raise ConflictError(
                f"This {self.label} is used by {in_use} existing record(s) and cannot be "
                f"deleted. Deactivate it instead so it stops appearing in new entries.",
            )

        instance.delete()
        self.on_commit(invalidate_masters)
        self.log("deleted", model=self.model.__name__)

    def _usage_count(self, instance) -> int:
        total = 0
        for model, field, value_attr in self.references:
            total += model.objects.filter(**{field: getattr(instance, value_attr)}).count()
        return total


class WorkTypeService(MasterDataService):
    model = WorkType
    label = "work type"

    @property
    def references(self):
        from apps.tracking.models import WorkSession

        return ((WorkSession, "work_type", "work_type"),)


class ProjectService(MasterDataService):
    model = Project
    label = "project"

    @property
    def references(self):
        from apps.tracking.models import WorkSession

        return ((WorkSession, "project", "project_name"),)


class ClientCodeService(MasterDataService):
    model = ClientCode
    label = "client code"

    @property
    def references(self):
        from apps.tracking.models import WorkSession

        return ((WorkSession, "client_code", "client_code"),)


class ShiftService(MasterDataService):
    model = Shift
    label = "shift"

    @property
    def references(self):
        from apps.accounts.models import Employee

        return ((Employee, "shift", "shift_name"),)


# ── cached read helpers ──────────────────────────────────────
# Used by the page context and the bundle endpoint. Invalidated wholesale by
# invalidate_masters() on any write.


@cached("masters")
def active_work_types() -> list[dict]:
    return list(WorkType.objects.active().values("id", "work_type", "standard_rate"))


@cached("masters")
def active_projects() -> list[dict]:
    return list(Project.objects.active().values("id", "project_id", "project_name", "project_code", "client_name"))


@cached("masters")
def active_client_codes() -> list[dict]:
    return list(ClientCode.objects.active().values("id", "client_code", "client_name", "project"))


@cached("masters")
def active_shifts() -> list[dict]:
    return list(Shift.objects.active().values("id", "shift_name", "start_time", "end_time"))
