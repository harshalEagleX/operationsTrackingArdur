"""Self-service signup: an employee HR already added sets their own password.

Found while pulling the latest main: both ``SignupView`` and
``CheckEmployeeView`` returned HTTP 500 on their error paths (``self.error()``
did not exist on ``EnvelopeMixin``, and ``SignupView`` referenced ``User``
without importing it). ``SignupView`` also wrote to the database directly
from the view and let anyone mint an account for an emp_id with no backing
``Employee`` row. These tests pin down the fixed behaviour.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import Employee, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def unregistered_employee(db) -> Employee:
    """An employee HR has added but who has never signed up."""
    return Employee.objects.create(
        employee_id="EMP900", name="New Hire", role="employee", status="active"
    )


# ── check-employee ───────────────────────────────────────────

def test_check_employee_returns_the_name_for_a_known_id(api, unregistered_employee):
    response = api.post("/api/v1/auth/check-employee/", {"emp_id": "EMP900"})

    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["data"]["name"] == "New Hire"


def test_check_employee_is_a_clean_404_not_a_crash(api):
    """This is the bug: an unknown id used to 500 because self.error() did
    not exist. It must come back as a proper domain 404."""
    response = api.post("/api/v1/auth/check-employee/", {"emp_id": "NOSUCHEMP"})

    assert response.status_code == 404
    assert response.data["ok"] is False
    assert response.data["error"]["code"] == "not_found"


def test_check_employee_does_not_offer_an_inactive_employee(api):
    Employee.objects.create(
        employee_id="EMP901", name="Left The Company", role="employee", status="inactive"
    )

    response = api.post("/api/v1/auth/check-employee/", {"emp_id": "EMP901"})
    assert response.status_code == 404


def test_check_employee_requires_no_authentication(api, unregistered_employee):
    """Public by design — it is what makes the signup page's autofill work
    before anyone has signed in."""
    assert api.post("/api/v1/auth/check-employee/", {"emp_id": "EMP900"}).status_code == 200


# ── signup ────────────────────────────────────────────────────

def test_signup_creates_a_working_login_for_an_existing_employee(api, unregistered_employee):
    response = api.post(
        "/api/v1/auth/signup/",
        {"emp_id": "EMP900", "name": "New Hire", "password": "a-strong-password-42"},
    )

    assert response.status_code == 201
    assert response.data["ok"] is True

    user = User.objects.get(emp_id="EMP900")
    assert user.check_password("a-strong-password-42")
    assert user.is_active

    # And the account can actually log in afterwards.
    login = api.post(
        "/api/v1/auth/login/", {"emp_id": "EMP900", "password": "a-strong-password-42"}
    )
    assert login.status_code == 200


def test_signup_rejects_an_emp_id_with_no_employee_record(api):
    """This is the access-control gap: signup used to create a login for any
    invented emp_id, bypassing admin-controlled employee creation entirely."""
    response = api.post(
        "/api/v1/auth/signup/",
        {"emp_id": "GHOST001", "name": "Nobody", "password": "a-strong-password-42"},
    )

    assert response.status_code == 404
    assert response.data["ok"] is False
    assert not User.objects.filter(emp_id="GHOST001").exists()


def test_signup_twice_for_the_same_employee_is_a_clean_409_not_a_crash(
    api, unregistered_employee
):
    """This is the other half of the original bug: a duplicate signup used to
    500 instead of reporting a conflict."""
    first = api.post(
        "/api/v1/auth/signup/",
        {"emp_id": "EMP900", "name": "New Hire", "password": "a-strong-password-42"},
    )
    assert first.status_code == 201

    second = api.post(
        "/api/v1/auth/signup/",
        {"emp_id": "EMP900", "name": "New Hire", "password": "another-strong-password-9"},
    )

    assert second.status_code == 409
    assert second.data["ok"] is False
    assert second.data["error"]["code"] == "conflict"


def test_signup_rejects_a_weak_password(api, unregistered_employee):
    response = api.post(
        "/api/v1/auth/signup/", {"emp_id": "EMP900", "name": "New Hire", "password": "123"}
    )

    assert response.status_code == 400
    assert not User.objects.filter(emp_id="EMP900").exists()


def test_signup_requires_no_authentication(api, unregistered_employee):
    response = api.post(
        "/api/v1/auth/signup/",
        {"emp_id": "EMP900", "name": "New Hire", "password": "a-strong-password-42"},
    )
    assert response.status_code == 201


def test_signup_does_not_write_to_the_database_outside_the_service_layer():
    """Architectural guard: SignupView must delegate to AuthService rather
    than calling User.objects.create() itself — see README 'The layering
    rule'. A regression here is a view bypassing business rules again."""
    import inspect

    from apps.accounts.views import SignupView

    source = inspect.getsource(SignupView)
    assert "AuthService()" in source
    assert "objects.create" not in source
