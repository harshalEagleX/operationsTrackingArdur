"""Management commands: dev-data seeding, load-test provisioning/cleanup,
and storage bootstrap.
"""

from __future__ import annotations

import io

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


# ── seed_dev ──────────────────────────────────────────────────

def test_seed_dev_creates_the_documented_accounts(settings):
    settings.DEBUG = True
    call_command("seed_dev", stdout=io.StringIO())

    from apps.accounts.models import Employee, User

    for emp_id in ("ADMIN01", "SUP01", "EMP01", "EMP02"):
        assert Employee.objects.filter(employee_id=emp_id).exists()
        assert User.objects.filter(emp_id=emp_id).exists()


def test_seed_dev_is_idempotent(settings):
    settings.DEBUG = True
    out = io.StringIO()
    call_command("seed_dev", stdout=out)
    call_command("seed_dev", stdout=out)  # must not raise (unique constraints, etc.)

    from apps.accounts.models import Employee

    assert Employee.objects.filter(employee_id="ADMIN01").count() == 1


def test_seed_dev_refuses_to_run_with_debug_false(settings):
    settings.DEBUG = False
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("seed_dev")


def test_seed_dev_force_overrides_the_debug_guard(settings):
    settings.DEBUG = False
    call_command("seed_dev", "--force", stdout=io.StringIO())

    from apps.accounts.models import Employee

    assert Employee.objects.filter(employee_id="ADMIN01").exists()


def test_seed_dev_seeds_master_data_and_settings(settings):
    settings.DEBUG = True
    call_command("seed_dev", stdout=io.StringIO())

    from apps.masters.models import ClientCode, Project, Shift, WorkType
    from apps.settings_app.models import AppSetting

    assert WorkType.objects.exists()
    assert Project.objects.exists()
    assert ClientCode.objects.exists()
    assert Shift.objects.exists()
    assert AppSetting.objects.exists()


def test_seed_dev_seeds_starter_allocations(settings):
    settings.DEBUG = True
    call_command("seed_dev", stdout=io.StringIO())

    from apps.allocations.models import BatchAllocation

    assert BatchAllocation.objects.filter(employee_id="EMP01").exists()


# ── seed_load_test / cleanup_load_test ───────────────────────

def test_seed_load_test_provisions_the_requested_counts(settings):
    settings.DEBUG = True
    call_command("seed_load_test", "--employees", "5", "--supervisors", "2", stdout=io.StringIO())

    from apps.accounts.models import Employee, User

    employees = Employee.objects.filter(employee_id__startswith="LOADT_LEMP")
    supervisors = Employee.objects.filter(employee_id__startswith="LOADT_LSUP")

    assert employees.count() == 5
    assert supervisors.count() == 2
    assert all(e.role == "employee" for e in employees)
    assert all(s.role == "supervisor" for s in supervisors)
    assert User.objects.filter(emp_id__startswith="LOADT_").count() == 7


def test_seed_load_test_spreads_employees_across_the_project_catalogue(settings):
    settings.DEBUG = True
    call_command("seed_load_test", "--employees", "20", "--supervisors", "1", stdout=io.StringIO())

    from apps.accounts.models import Employee
    from apps.masters.models import ClientCode, Project

    assert Project.objects.filter(project_name__startswith="Load Test —").count() == 50
    assert ClientCode.objects.filter(client_code__startswith="LT-CC-").count() == 15

    projects_used = set(
        Employee.objects.filter(employee_id__startswith="LOADT_LEMP").values_list(
            "project", flat=True
        )
    )
    assert len(projects_used) > 1  # not everyone piled onto the same project


def test_seed_load_test_is_idempotent(settings):
    settings.DEBUG = True
    call_command("seed_load_test", "--employees", "3", "--supervisors", "1", stdout=io.StringIO())
    call_command("seed_load_test", "--employees", "3", "--supervisors", "1", stdout=io.StringIO())

    from apps.accounts.models import Employee

    assert Employee.objects.filter(employee_id__startswith="LOADT_LEMP").count() == 3


def test_seed_load_test_refuses_debug_false(settings):
    settings.DEBUG = False
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("seed_load_test")


def test_cleanup_load_test_removes_everything_it_provisioned(settings):
    settings.DEBUG = True
    call_command("seed_load_test", "--employees", "4", "--supervisors", "1", stdout=io.StringIO())

    from apps.accounts.models import Employee, User

    call_command("cleanup_load_test", stdout=io.StringIO())

    assert not Employee.objects.filter(employee_id__startswith="LOADT_").exists()
    assert not User.objects.filter(emp_id__startswith="LOADT_").exists()


def test_cleanup_load_test_also_removes_dependent_records(settings):
    settings.DEBUG = True
    call_command("seed_load_test", "--employees", "2", "--supervisors", "1", stdout=io.StringIO())

    from apps.accounts.models import Employee
    from apps.breaks.models import BreakTime
    from apps.tracking.models import SessionState, WorkSession

    emp_id = Employee.objects.filter(employee_id__startswith="LOADT_LEMP").first().employee_id
    WorkSession.objects.create(emp_id=emp_id, project="P", is_started=SessionState.RUNNING)
    BreakTime.objects.create(user_id=emp_id, break_type="Tea break 1")

    call_command("cleanup_load_test", stdout=io.StringIO())

    assert not WorkSession.objects.filter(emp_id=emp_id).exists()
    assert not BreakTime.objects.filter(user_id=emp_id).exists()


def test_cleanup_load_test_leaves_seed_dev_accounts_alone(settings):
    settings.DEBUG = True
    call_command("seed_dev", stdout=io.StringIO())
    call_command("seed_load_test", "--employees", "1", "--supervisors", "0", stdout=io.StringIO())

    call_command("cleanup_load_test", stdout=io.StringIO())

    from apps.accounts.models import Employee

    assert Employee.objects.filter(employee_id="EMP01").exists()


def test_cleanup_load_test_on_an_empty_database_does_not_raise():
    call_command("cleanup_load_test", stdout=io.StringIO())


# ── bootstrap_storage ─────────────────────────────────────────

def test_bootstrap_storage_creates_the_expected_tree(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private-storage"
    call_command("bootstrap_storage", stdout=io.StringIO())

    root = tmp_path / "private-storage"
    for sub in ("uploads/feedback", "uploads/allocations", "uploads/chat", "uploads/misc",
                "thumbs", "exports"):
        assert (root / sub).is_dir()


def test_bootstrap_storage_warns_when_the_root_is_inside_static_root(settings, tmp_path):
    settings.STATIC_ROOT = tmp_path / "shared"
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "shared" / "private"

    out = io.StringIO()
    call_command("bootstrap_storage", stdout=out)

    assert "publicly downloadable" in out.getvalue()


def test_bootstrap_storage_is_idempotent(settings, tmp_path):
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private-storage"
    call_command("bootstrap_storage", stdout=io.StringIO())
    call_command("bootstrap_storage", stdout=io.StringIO())  # must not raise
