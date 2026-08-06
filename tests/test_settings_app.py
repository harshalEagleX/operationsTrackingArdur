"""Runtime-editable application settings."""

from __future__ import annotations

import pytest

from apps.settings_app.models import AppSetting, ValueType
from apps.settings_app.services import DEFAULTS, SettingsService
from core.exceptions import NotFoundError, PermissionDeniedError, ValidationError

pytestmark = pytest.mark.django_db


# ── typed_value coercion ──────────────────────────────────────

def test_typed_value_coerces_integer():
    setting = AppSetting(key="x", value="42", value_type=ValueType.INTEGER)
    assert setting.typed_value == 42


def test_typed_value_integer_falls_back_to_zero_on_garbage():
    """A bad value must not take the application down at import time."""
    setting = AppSetting(key="x", value="not-a-number", value_type=ValueType.INTEGER)
    assert setting.typed_value == 0


def test_typed_value_coerces_boolean_truthy_strings():
    for raw in ("1", "true", "True", "yes", "on"):
        assert AppSetting(key="x", value=raw, value_type=ValueType.BOOLEAN).typed_value is True


def test_typed_value_coerces_boolean_falsy_strings():
    for raw in ("0", "false", "no", "", "off", "garbage"):
        assert AppSetting(key="x", value=raw, value_type=ValueType.BOOLEAN).typed_value is False


def test_typed_value_coerces_json():
    setting = AppSetting(key="x", value='{"a": 1}', value_type=ValueType.JSON)
    assert setting.typed_value == {"a": 1}


def test_typed_value_json_falls_back_to_empty_dict_on_garbage():
    setting = AppSetting(key="x", value="{not json", value_type=ValueType.JSON)
    assert setting.typed_value == {}


def test_typed_value_string_is_passed_through():
    setting = AppSetting(key="x", value="hello", value_type=ValueType.STRING)
    assert setting.typed_value == "hello"


# ── seed_defaults ─────────────────────────────────────────────

def test_seed_defaults_creates_every_default():
    created = SettingsService.seed_defaults()
    assert created == len(DEFAULTS)
    assert AppSetting.objects.count() == len(DEFAULTS)


def test_seed_defaults_is_idempotent():
    SettingsService.seed_defaults()
    second_run = SettingsService.seed_defaults()
    assert second_run == 0
    assert AppSetting.objects.count() == len(DEFAULTS)


# ── get() / caching ───────────────────────────────────────────

def test_get_returns_the_default_when_no_row_exists():
    assert SettingsService.get("no.such.key", default="fallback") == "fallback"


def test_get_returns_the_typed_stored_value():
    AppSetting.objects.create(key="work.idle_warning_minutes", value="20", value_type=ValueType.INTEGER)
    assert SettingsService.get("work.idle_warning_minutes") == 20


def test_get_is_cached_until_bumped(admin):
    AppSetting.objects.create(key="app.company_name", value="Acme", value_type=ValueType.STRING)
    assert SettingsService.get("app.company_name") == "Acme"

    # Mutate the row directly, bypassing the service — the cached value
    # should still be served until something bumps the namespace.
    AppSetting.objects.filter(key="app.company_name").update(value="Other Co")
    assert SettingsService.get("app.company_name") == "Acme"


def test_set_bumps_the_cache_on_commit(django_capture_on_commit_callbacks, admin):
    setting = AppSetting.objects.create(
        key="app.company_name", value="Acme", value_type=ValueType.STRING
    )
    SettingsService.get("app.company_name")  # warm the cache

    with django_capture_on_commit_callbacks(execute=True):
        SettingsService(actor=admin).set(setting.key, "New Name")

    assert SettingsService.get("app.company_name") == "New Name"


def test_all_settings_returns_every_row_typed():
    AppSetting.objects.create(key="a", value="1", value_type=ValueType.INTEGER)
    AppSetting.objects.create(key="b", value="true", value_type=ValueType.BOOLEAN)

    result = SettingsService.all_settings()
    assert result == {"a": 1, "b": True}


# ── set(): permissions and validation ────────────────────────

def test_only_an_admin_can_change_a_setting(supervisor):
    setting = AppSetting.objects.create(key="x", value="1", value_type=ValueType.STRING)
    with pytest.raises(PermissionDeniedError):
        SettingsService(actor=supervisor).set(setting.key, "2")


def test_setting_a_nonexistent_key_is_a_404(admin):
    with pytest.raises(NotFoundError):
        SettingsService(actor=admin).set("no.such.key", "value")


def test_a_non_editable_setting_is_rejected(admin):
    setting = AppSetting.objects.create(
        key="x", value="1", value_type=ValueType.STRING, is_editable=False
    )
    with pytest.raises(ValidationError):
        SettingsService(actor=admin).set(setting.key, "2")


def test_an_integer_setting_rejects_non_numeric_input(admin):
    setting = AppSetting.objects.create(key="x", value="1", value_type=ValueType.INTEGER)
    with pytest.raises(ValidationError):
        SettingsService(actor=admin).set(setting.key, "not-a-number")


def test_a_json_setting_rejects_invalid_json(admin):
    setting = AppSetting.objects.create(key="x", value="{}", value_type=ValueType.JSON)
    with pytest.raises(ValidationError):
        SettingsService(actor=admin).set(setting.key, "{not json")


def test_set_records_who_changed_it(admin):
    setting = AppSetting.objects.create(key="x", value="1", value_type=ValueType.STRING)
    updated = SettingsService(actor=admin).set(setting.key, "2")

    assert updated.value == "2"
    assert updated.updated_by == admin.emp_id


# ── HTTP ─────────────────────────────────────────────────────

def test_employee_can_read_settings(as_employee):
    AppSetting.objects.create(key="x", value="1", value_type=ValueType.STRING)
    response = as_employee.get("/api/v1/settings/")
    assert response.status_code == 200


def test_employee_cannot_write_settings(as_employee):
    setting = AppSetting.objects.create(key="x", value="1", value_type=ValueType.STRING)
    response = as_employee.post("/api/v1/settings/set/", {"key": setting.key, "value": "2"})
    assert response.status_code == 403


def test_admin_can_write_settings_over_http(as_admin):
    setting = AppSetting.objects.create(key="x", value="1", value_type=ValueType.STRING)
    response = as_admin.post("/api/v1/settings/set/", {"key": setting.key, "value": "2"})

    assert response.status_code == 200
    assert response.data["data"]["value"] == "2"


def test_as_map_endpoint_returns_a_flat_dict(as_employee):
    AppSetting.objects.create(key="app.company_name", value="Acme", value_type=ValueType.STRING)
    response = as_employee.get("/api/v1/settings/map/")

    assert response.status_code == 200
    assert response.data["data"]["app.company_name"] == "Acme"


def test_settings_filter_by_category(as_employee):
    AppSetting.objects.create(key="a", value="1", category="tracking")
    AppSetting.objects.create(key="b", value="2", category="reports")

    response = as_employee.get("/api/v1/settings/", {"category": "tracking"})
    keys = [row["key"] for row in response.data["data"]]

    assert keys == ["a"]


def test_settings_endpoints_reject_anonymous_requests(api):
    assert api.get("/api/v1/settings/").status_code in (401, 403)
