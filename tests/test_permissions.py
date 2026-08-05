"""Authorisation boundaries.

Each test here corresponds to a way the previous application could be made to
hand over data or accept a write it should have refused.
"""

from __future__ import annotations

import pytest

from apps.feedback.models import Feedback
from apps.masters.models import Project

pytestmark = pytest.mark.django_db


# ── master data is admin-write, everyone-read ────────────────

def test_employee_can_read_master_data(as_employee, masters):
    assert as_employee.get("/api/v1/masters/projects/").status_code == 200


def test_employee_cannot_create_a_project(as_employee):
    response = as_employee.post(
        "/api/v1/masters/projects/", {"project_name": "Sneaky Project"}
    )

    assert response.status_code == 403
    assert not Project.objects.filter(project_name="Sneaky Project").exists()


def test_employee_cannot_delete_a_project(as_employee, masters):
    response = as_employee.delete(f"/api/v1/masters/projects/{masters['project'].id}/")

    assert response.status_code == 403


def test_supervisor_cannot_create_a_project(as_supervisor):
    """Master data is admin-only — supervisors manage people, not the schema."""
    assert as_supervisor.post(
        "/api/v1/masters/projects/", {"project_name": "Supervisor Project"}
    ).status_code == 403


def test_admin_can_create_a_project(as_admin):
    response = as_admin.post("/api/v1/masters/projects/", {"project_name": "Real Project"})

    assert response.status_code == 201
    assert Project.objects.filter(project_name="Real Project").exists()


# ── allocations are supervisor-write ─────────────────────────

def test_employee_cannot_create_an_allocation(as_employee, employee):
    response = as_employee.post(
        "/api/v1/allocations/",
        {"allocation_id": "SELF-001", "employee_id": employee.emp_id, "quantity": 100},
    )

    assert response.status_code == 403


def test_supervisor_can_create_an_allocation(as_supervisor, employee):
    response = as_supervisor.post(
        "/api/v1/allocations/",
        {"allocation_id": "ALLOC-001", "employee_id": employee.emp_id, "quantity": 100},
    )

    assert response.status_code == 201


# ── feedback is not readable across employees ────────────────

def test_employee_cannot_read_another_employees_feedback(
    as_employee, employee, other_employee, supervisor
):
    feedback = Feedback.objects.create(
        emp_id=other_employee.emp_id,
        subject="Confidential coaching note",
        created_by=supervisor.emp_id,
    )

    detail = as_employee.get(f"/api/v1/feedback/{feedback.id}/")
    assert detail.status_code in (403, 404)

    # And it must not leak through the list either — an object permission
    # never runs on a list endpoint.
    listing = as_employee.get("/api/v1/feedback/")
    returned = [row["id"] for row in listing.data["data"]]
    assert feedback.id not in returned


def test_employee_can_read_their_own_feedback(as_employee, employee, supervisor):
    feedback = Feedback.objects.create(
        emp_id=employee.emp_id, subject="Your own note", created_by=supervisor.emp_id
    )

    response = as_employee.get(f"/api/v1/feedback/{feedback.id}/")
    assert response.status_code == 200


def test_supervisor_sees_all_feedback(as_supervisor, other_employee, admin):
    Feedback.objects.create(
        emp_id=other_employee.emp_id, subject="A note", created_by=admin.emp_id
    )

    response = as_supervisor.get("/api/v1/feedback/")
    assert len(response.data["data"]) == 1


def test_employee_cannot_create_feedback(as_employee, other_employee):
    response = as_employee.post(
        "/api/v1/feedback/", {"emp_id": other_employee.emp_id, "subject": "Made up"}
    )

    assert response.status_code == 403


# ── work sessions are scoped to their owner ──────────────────

def test_employee_cannot_list_another_employees_sessions(
    as_employee, other_employee, masters
):
    from apps.tracking.models import SessionState, WorkSession

    session = WorkSession.objects.create(
        emp_id=other_employee.emp_id, project="Test Project",
        is_started=SessionState.RUNNING,
    )

    response = as_employee.get("/api/v1/tracking/sessions/")
    returned = [row["id"] for row in response.data["data"]]

    assert session.id not in returned


def test_employee_cannot_view_another_persons_dashboard(as_employee, other_employee):
    response = as_employee.get(
        "/api/v1/tracking/summary/", {"emp_id": other_employee.emp_id}
    )

    assert response.status_code == 403


# ── unauthenticated access ───────────────────────────────────

@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/me/",
        "/api/v1/auth/employees/",
        "/api/v1/masters/projects/",
        "/api/v1/tracking/sessions/",
        "/api/v1/breaks/",
        "/api/v1/allocations/",
        "/api/v1/feedback/",
        "/api/v1/reports/",
        "/api/v1/presence/",
        "/api/v1/notifications/",
    ],
)
def test_endpoints_reject_anonymous_requests(api, path):
    """Deny-by-default, verified endpoint by endpoint."""
    assert api.get(path).status_code in (401, 403)
