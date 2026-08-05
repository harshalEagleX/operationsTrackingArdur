"""Runtime-editable application settings.

For values an administrator should be able to change without a deploy. Things
that must NOT live here: break allowances (a user-editable allowance is a
user-editable payroll figure), permission rules, and anything security-
relevant. Those belong in code where they are reviewed and version-controlled.
"""

from __future__ import annotations

from django.db import models

from core.models import legacy_managed
from core.timezone import now_ist


class ValueType(models.TextChoices):
    STRING = "string", "Text"
    INTEGER = "integer", "Number"
    BOOLEAN = "boolean", "Yes/No"
    JSON = "json", "JSON"


class AppSetting(models.Model):
    id = models.AutoField(primary_key=True)
    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.TextField(blank=True, default="")
    value_type = models.CharField(
        max_length=10, choices=ValueType.choices, default=ValueType.STRING
    )
    label = models.CharField(max_length=150, blank=True, default="")
    description = models.CharField(max_length=500, blank=True, default="")
    category = models.CharField(max_length=50, blank=True, default="general", db_index=True)
    is_editable = models.BooleanField(default=True)

    updated_by = models.CharField(max_length=20, blank=True, default="")
    updated_at = models.DateTimeField(default=now_ist)

    class Meta:
        managed = legacy_managed()
        db_table = "ot_app_settings"
        ordering = ["category", "key"]

    def __str__(self) -> str:
        return f"{self.key} = {self.value[:40]}"

    @property
    def typed_value(self):
        """Coerce the stored string to its declared type.

        A bad value returns the raw string rather than raising — one malformed
        setting must not take the application down at import time.
        """
        if self.value_type == ValueType.INTEGER:
            try:
                return int(self.value)
            except (TypeError, ValueError):
                return 0
        if self.value_type == ValueType.BOOLEAN:
            return str(self.value).strip().lower() in ("1", "true", "yes", "on")
        if self.value_type == ValueType.JSON:
            import json

            try:
                return json.loads(self.value or "{}")
            except (TypeError, ValueError):
                return {}
        return self.value
