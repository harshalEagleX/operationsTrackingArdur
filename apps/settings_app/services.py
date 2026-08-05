"""Application settings service."""

from __future__ import annotations

from django.db import transaction

from apps.settings_app.models import AppSetting, ValueType
from core.cache import bump, get_or_set
from core.exceptions import ValidationError
from core.services import BaseService
from core.timezone import now_ist

CACHE_NAMESPACE = "appsettings"

# Settings that ship with the application. Seeded on first run; an admin can
# change the values but not the set.
DEFAULTS = [
    ("app.company_name", "OpsTracking", ValueType.STRING, "Company name",
     "Shown in the page header and on exports", "branding"),
    ("app.support_email", "", ValueType.STRING, "Support email",
     "Where the 'contact support' link points", "branding"),
    ("work.idle_warning_minutes", "15", ValueType.INTEGER, "Idle warning (minutes)",
     "How long a running session may sit with no activity before warning", "tracking"),
    ("work.require_batch", "false", ValueType.BOOLEAN, "Batch required",
     "Require a batch reference when starting a work session", "tracking"),
    ("reports.default_range_days", "7", ValueType.INTEGER, "Default report range",
     "How many days a report covers when no dates are given", "reports"),
    ("notifications.digest_hour", "20", ValueType.INTEGER, "Digest hour",
     "Hour of day (IST) the supervisor digest is sent", "notifications"),
]


class SettingsService(BaseService):
    """Read and write application settings."""

    @staticmethod
    def get(key: str, default=None):
        """Cached read. Used on hot paths, so it must not hit the database
        on every request."""

        def load():
            setting = AppSetting.objects.filter(key=key).first()
            return setting.typed_value if setting else default

        return get_or_set(CACHE_NAMESPACE, (key,), load, ttl=300)

    @staticmethod
    def all_settings() -> dict:
        return {s.key: s.typed_value for s in AppSetting.objects.all()}

    @transaction.atomic
    def set(self, key: str, value) -> AppSetting:
        self.require_admin("Only an administrator can change application settings.")

        setting = self.require_found(
            AppSetting.objects.filter(key=key).first(), f"No setting named '{key}'."
        )

        if not setting.is_editable:
            raise ValidationError(f"'{key}' is not editable at runtime.")

        self._validate(setting, value)

        setting.value = str(value)
        setting.updated_by = self.actor_emp_id or ""
        setting.updated_at = now_ist()
        setting.save(update_fields=["value", "updated_by", "updated_at"])

        self.on_commit(lambda: bump(CACHE_NAMESPACE))
        self.log("setting_changed", key=key)
        return setting

    @staticmethod
    def _validate(setting: AppSetting, value) -> None:
        if setting.value_type == ValueType.INTEGER:
            try:
                int(value)
            except (TypeError, ValueError):
                raise ValidationError(f"'{setting.key}' must be a whole number.") from None
        elif setting.value_type == ValueType.JSON:
            import json

            try:
                json.loads(str(value))
            except (TypeError, ValueError):
                raise ValidationError(f"'{setting.key}' must be valid JSON.") from None

    @classmethod
    def seed_defaults(cls) -> int:
        """Create any missing default settings. Idempotent — safe on deploy."""
        created = 0
        for key, value, value_type, label, description, category in DEFAULTS:
            _, was_created = AppSetting.objects.get_or_create(
                key=key,
                defaults={
                    "value": value,
                    "value_type": value_type,
                    "label": label,
                    "description": description,
                    "category": category,
                },
            )
            created += int(was_created)

        if created:
            bump(CACHE_NAMESPACE)
        return created
