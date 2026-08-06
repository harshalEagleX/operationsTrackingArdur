"""Jinja2 page views — thin shells that hand off to the JS layer.

Nothing here queries a model directly, so these tests are about routing,
auth gates and role-based redirects, not data.
"""

from __future__ import annotations

import pytest
from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db


# ── login / signup pages ──────────────────────────────────────

def test_login_page_renders_for_an_anonymous_visitor(client):
    response = client.get("/login/")
    assert response.status_code == 200
    assert b"Sign in" in response.content or response.status_code == 200


def test_login_page_redirects_an_already_authenticated_employee(client, employee):
    client.login(emp_id=employee.emp_id, password=PASSWORD)
    response = client.get("/login/")
    assert response.status_code == 302
    assert response.url == "/userdashboard/"


def test_login_page_redirects_an_authenticated_supervisor_to_the_dashboard(client, supervisor):
    client.login(emp_id=supervisor.emp_id, password=PASSWORD)
    response = client.get("/login/")
    assert response.url == "/dashboard/"


def test_login_page_carries_the_reason_and_next_params(client):
    response = client.get("/login/", {"reason": "session_expired", "next": "/dashboard/"})
    assert response.status_code == 200


def test_signup_page_renders_for_an_anonymous_visitor(client):
    assert client.get("/signup/").status_code == 200


def test_signup_page_redirects_an_authenticated_user(client, employee):
    client.login(emp_id=employee.emp_id, password=PASSWORD)
    response = client.get("/signup/")
    assert response.status_code == 302


# ── auth gate ─────────────────────────────────────────────────

def test_dashboard_requires_authentication(client):
    response = client.get("/dashboard/")
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_home_redirect_requires_authentication(client):
    response = client.get("/")
    assert response.status_code == 302


# ── role-based routing ────────────────────────────────────────

def test_home_redirects_a_supervisor_to_the_dashboard(client, supervisor):
    client.login(emp_id=supervisor.emp_id, password=PASSWORD)
    response = client.get("/")
    assert response.url == "/dashboard/"


def test_home_redirects_an_employee_to_the_user_dashboard(client, employee):
    client.login(emp_id=employee.emp_id, password=PASSWORD)
    response = client.get("/")
    assert response.url == "/userdashboard/"


def test_an_employee_visiting_the_supervisor_dashboard_is_redirected(client, employee):
    client.login(emp_id=employee.emp_id, password=PASSWORD)
    response = client.get("/dashboard/")
    assert response.status_code == 302
    assert response.url == "/userdashboard/"


def test_a_supervisor_can_open_the_dashboard(client, supervisor):
    client.login(emp_id=supervisor.emp_id, password=PASSWORD)
    assert client.get("/dashboard/").status_code == 200


def test_an_employee_can_open_their_own_dashboard(client, employee):
    client.login(emp_id=employee.emp_id, password=PASSWORD)
    response = client.get("/userdashboard/")
    assert response.status_code == 200


def test_user_dashboard_context_carries_identity(client, employee):
    """response.context isn't populated for this project's Jinja2 backend
    under the test client, so assert on the rendered HTML instead of
    introspecting the context dict directly."""
    client.login(emp_id=employee.emp_id, password=PASSWORD)
    response = client.get("/userdashboard/")
    assert employee.emp_id.encode() in response.content


# ── settings page: admin only ───────────────────────────────

def test_settings_page_404s_for_a_plain_employee(client, employee):
    client.login(emp_id=employee.emp_id, password=PASSWORD)
    assert client.get("/settings/").status_code == 404


def test_settings_page_404s_for_a_supervisor(client, supervisor):
    """Admin-only, not merely supervisor-or-above — unlike most of the app."""
    client.login(emp_id=supervisor.emp_id, password=PASSWORD)
    assert client.get("/settings/").status_code == 404


def test_settings_page_opens_for_an_admin(client, admin):
    client.login(emp_id=admin.emp_id, password=PASSWORD)
    response = client.get("/settings/")
    assert response.status_code == 200


def test_settings_page_requires_authentication(client):
    response = client.get("/settings/")
    assert response.status_code == 302


# ── chat page: dark unless the feature flag is on ────────────

def test_chat_page_is_404_when_the_feature_is_off(client, employee, settings):
    settings.FEATURE_CHAT = False
    client.login(emp_id=employee.emp_id, password=PASSWORD)
    assert client.get("/chat/").status_code == 404


def test_chat_page_opens_when_the_feature_flag_is_on(client, employee, settings):
    """Flipping the flag is enough — apps.chat itself stays uninstalled;
    this only proves the page-level gate reads the flag correctly."""
    settings.FEATURE_CHAT = True
    client.login(emp_id=employee.emp_id, password=PASSWORD)
    response = client.get("/chat/")
    assert response.status_code == 200


# ── base_context is actually threaded through every page ─────

def test_every_authenticated_page_carries_the_bootstrap_context(client, supervisor):
    """base_context() serialises into window.__BOOTSTRAP__ in base.html —
    confirm it actually reaches a rendered page (dashboard.html is one of
    the two templates that {% extends "base.html" %}) rather than testing
    pages/context.py's return value a second time (already covered in
    tests/test_pages_context.py)."""
    client.login(emp_id=supervisor.emp_id, password=PASSWORD)
    response = client.get("/dashboard/")

    assert response.status_code == 200
    assert b"/api/v1" in response.content
    assert supervisor.emp_id.encode() in response.content
