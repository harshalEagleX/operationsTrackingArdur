"""Authentication and session behaviour."""

from __future__ import annotations

import pytest

from apps.accounts.models import LoginHistory, User
from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db


def test_login_succeeds_with_correct_credentials(api, employee):
    response = api.post(
        "/api/v1/auth/login/", {"emp_id": employee.emp_id, "password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["data"]["emp_id"] == employee.emp_id


def test_login_records_history(api, employee):
    api.post("/api/v1/auth/login/", {"emp_id": employee.emp_id, "password": PASSWORD})

    assert LoginHistory.objects.filter(emp_id=employee.emp_id).exists()


def test_login_fails_with_wrong_password(api, employee):
    response = api.post(
        "/api/v1/auth/login/", {"emp_id": employee.emp_id, "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.data["ok"] is False


def test_login_failure_does_not_reveal_whether_the_user_exists(api, employee):
    """A distinguishable response is a free employee-ID oracle."""
    wrong_password = api.post(
        "/api/v1/auth/login/", {"emp_id": employee.emp_id, "password": "wrong"}
    )
    no_such_user = api.post(
        "/api/v1/auth/login/", {"emp_id": "NOBODY99", "password": "wrong"}
    )

    assert wrong_password.status_code == no_such_user.status_code
    assert wrong_password.data["error"]["message"] == no_such_user.data["error"]["message"]


def test_deactivated_account_cannot_sign_in(api, employee):
    User.objects.filter(pk=employee.pk).update(status="inactive")

    response = api.post(
        "/api/v1/auth/login/", {"emp_id": employee.emp_id, "password": PASSWORD}
    )

    assert response.status_code == 401


def test_session_is_invalid_after_logout(api, employee):
    """The core of the logout fix: the session row is deleted, so a replayed
    cookie resolves to nothing."""
    api.post("/api/v1/auth/login/", {"emp_id": employee.emp_id, "password": PASSWORD})
    assert api.get("/api/v1/auth/me/").status_code == 200

    api.post("/api/v1/auth/logout/")

    assert api.get("/api/v1/auth/me/").status_code == 403


def test_logout_closes_open_login_history(api, employee):
    api.post("/api/v1/auth/login/", {"emp_id": employee.emp_id, "password": PASSWORD})
    api.post("/api/v1/auth/logout/")

    assert not LoginHistory.objects.filter(
        emp_id=employee.emp_id, logout_time__isnull=True
    ).exists()


def test_me_requires_authentication(api):
    assert api.get("/api/v1/auth/me/").status_code == 403


def test_password_change_requires_the_current_password(as_employee):
    response = as_employee.post(
        "/api/v1/auth/password/change/",
        {
            "current_password": "not-the-password",
            "new_password": "brand-new-password-9",
            "confirm_password": "brand-new-password-9",
        },
    )

    assert response.status_code == 401


def test_password_change_succeeds(as_employee, employee):
    response = as_employee.post(
        "/api/v1/auth/password/change/",
        {
            "current_password": PASSWORD,
            "new_password": "brand-new-password-9",
            "confirm_password": "brand-new-password-9",
        },
    )

    assert response.status_code == 200
    employee.refresh_from_db()
    assert employee.check_password("brand-new-password-9")


def test_employee_cannot_reset_another_persons_password(as_employee, other_employee):
    response = as_employee.post(
        "/api/v1/auth/password/reset/",
        {"emp_id": other_employee.emp_id, "new_password": "hijacked-password-1"},
    )

    assert response.status_code == 403
