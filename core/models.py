"""Abstract model bases.

``core`` deliberately declares no concrete models — it has no table of its own
and no migrations. These are mixins for the apps to inherit.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.timezone import now_ist


def legacy_managed() -> bool:
    """Whether Django owns the schema of the tables inherited from Flask.

    True locally (migrations create them so a fresh clone has a working
    database); False in production (the tables already hold live data and
    Django must never issue DDL against them).

    Read at class-definition time, which is after settings are loaded.
    """
    return settings.LEGACY_TABLES_MANAGED


class TimeStampedModel(models.Model):  # pragma: no cover — no concrete model inherits this yet
    """created_at / updated_at, both IST.

    Uses ``default=now_ist`` rather than ``auto_now_add`` so that an import
    script can set a historical timestamp — auto_now_add silently overwrites
    whatever you pass it, which makes back-filling impossible.
    """

    created_at = models.DateTimeField(default=now_ist, editable=False)
    updated_at = models.DateTimeField(default=now_ist)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        self.updated_at = now_ist()
        if update_fields is not None and "updated_at" not in update_fields:
            kwargs["update_fields"] = [*update_fields, "updated_at"]
        super().save(*args, **kwargs)


class SoftDeleteModel(models.Model):  # pragma: no cover — no concrete model inherits this yet
    """A nullable deleted_at plus the manager pair.

    Records referenced by reports are never hard-deleted — a work session that
    vanishes changes last month's numbers retroactively.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self, save: bool = True) -> None:
        self.deleted_at = now_ist()
        if save:
            self.save(update_fields=["deleted_at"])

    def restore(self, save: bool = True) -> None:
        self.deleted_at = None
        if save:
            self.save(update_fields=["deleted_at"])


class ActorStampedModel(models.Model):  # pragma: no cover — no concrete model inherits this yet
    """Who created and who last touched the row, by employee id.

    Stored as a plain CharField rather than an FK: the legacy tables key on
    ``emp_id`` strings, and an employee who leaves must not cascade-delete
    their audit trail.
    """

    created_by = models.CharField(max_length=20, blank=True, default="")
    updated_by = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        abstract = True
