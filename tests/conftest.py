"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Employee, User
from apps.masters.models import ClientCode, Project, WorkType

PASSWORD = "test-password-123"


@pytest.fixture(autouse=True)
def _clear_cache():
    """LocMemCache is a process-global dict, not tied to the per-test DB
    transaction — without this, a cached() value (master data, app settings,
    presence state) from one test leaks into the next and produces flaky
    failures that have nothing to do with what that test actually exercises."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


def _make_user(emp_id: str, name: str, role: str) -> User:
    Employee.objects.create(
        employee_id=emp_id, name=name, role=role, project="Test Project", status="active"
    )
    return User.objects.create_user(emp_id=emp_id, password=PASSWORD, name=name)


@pytest.fixture
def employee(db) -> User:
    return _make_user("EMP001", "Test Employee", "employee")


@pytest.fixture
def other_employee(db) -> User:
    """A second employee — needed to prove one cannot read the other's data."""
    return _make_user("EMP002", "Other Employee", "employee")


@pytest.fixture
def supervisor(db) -> User:
    return _make_user("SUP001", "Test Supervisor", "supervisor")


@pytest.fixture
def admin(db) -> User:
    return _make_user("ADM001", "Test Admin", "admin")


@pytest.fixture
def as_employee(api, employee) -> APIClient:
    api.force_authenticate(user=employee)
    return api


@pytest.fixture
def as_supervisor(api, supervisor) -> APIClient:
    api.force_authenticate(user=supervisor)
    return api


@pytest.fixture
def as_admin(api, admin) -> APIClient:
    api.force_authenticate(user=admin)
    return api


@pytest.fixture
def masters(db):
    """The minimum master data a work session needs."""
    return {
        "work_type": WorkType.objects.create(work_type="Data entry"),
        "project": Project.objects.create(project_name="Test Project"),
        "client_code": ClientCode.objects.create(client_code="TST-001"),
    }
