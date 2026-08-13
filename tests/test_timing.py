"""Server-side timing.

The browser clock is attacker-controlled and anything derived from it lands in
a report someone gets paid against. These tests pin that down.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from apps.tracking.models import SessionState, WorkSession
from apps.tracking.services import WorkSessionService
from core.exceptions import ConflictError
from core.timezone import IST, now_ist, today_ist

pytestmark = pytest.mark.django_db


def test_end_time_is_server_generated(as_employee, employee, masters):
    """A client-supplied end_time must be ignored, not trusted."""
    session = WorkSession.objects.create(
        emp_id=employee.emp_id, project="Test Project",
        start_time=now_ist() - timedelta(hours=1),
        is_started=SessionState.RUNNING,
    )

    forged = now_ist() + timedelta(hours=99)
    response = as_employee.post(
        f"/api/v1/tracking/sessions/{session.id}/end/",
        {"end_time": forged.isoformat(), "total_time": 999999},
    )

    assert response.status_code == 200
    session.refresh_from_db()

    assert session.end_time < forged
    # An hour of work, give or take the test's own runtime.
    assert 3500 < session.total_time < 3700


def test_total_time_excludes_paused_periods(employee, masters):
    service = WorkSessionService(actor=employee)

    session = WorkSession.objects.create(
        emp_id=employee.emp_id, project="Test Project",
        start_time=now_ist() - timedelta(minutes=60),
        paused_elapsed=600,  # ten minutes already banked
        is_started=SessionState.RUNNING,
    )

    finished = service.end_session(session.id)

    # 60 minutes elapsed minus 10 paused = 50 minutes of work.
    assert 2950 < finished.total_time < 3050


def test_average_time_is_derived_not_supplied(employee, masters):
    service = WorkSessionService(actor=employee)

    session = WorkSession.objects.create(
        emp_id=employee.emp_id, project="Test Project",
        start_time=now_ist() - timedelta(seconds=100),
        is_started=SessionState.RUNNING,
    )

    finished = service.end_session(session.id)

    assert finished.average_time == pytest.approx(finished.total_time / 10, abs=0.1)


def test_zero_work_units_leaves_average_null(employee, masters):
    """Guarding the division, not crashing on it."""
    service = WorkSessionService(actor=employee)

    session = WorkSession.objects.create(
        emp_id=employee.emp_id, project="Test Project",
        start_time=now_ist() - timedelta(seconds=60),
        is_started=SessionState.RUNNING,
    )

    finished = service.end_session(session.id)
    assert finished.average_time is None


def test_only_one_session_may_be_open_per_employee(employee, masters):
    service = WorkSessionService(actor=employee)
    service.start_session(project="Test Project", work_type="Data entry")

    with pytest.raises(ConflictError):
        service.start_session(project="Test Project", work_type="Data entry")


def test_pause_then_resume_accumulates_paused_time(employee, masters):
    service = WorkSessionService(actor=employee)

    session = service.start_session(project="Test Project", work_type="Data entry")
    service.pause_session(session.id)

    paused = WorkSession.objects.get(pk=session.id)
    assert paused.is_paused is True
    assert paused.paused_at is not None

    service.resume_session(session.id)

    resumed = WorkSession.objects.get(pk=session.id)
    assert resumed.is_paused is False
    assert resumed.paused_at is None
    assert resumed.paused_elapsed >= 0


def test_a_session_cannot_be_paused_twice(employee, masters):
    service = WorkSessionService(actor=employee)
    session = service.start_session(project="Test Project", work_type="Data entry")
    service.pause_session(session.id)

    with pytest.raises(ConflictError):
        service.pause_session(session.id)


def test_employee_cannot_end_another_persons_session(employee, other_employee, masters):
    session = WorkSession.objects.create(
        emp_id=other_employee.emp_id, project="Test Project",
        is_started=SessionState.RUNNING,
    )

    from core.exceptions import PermissionDeniedError

    with pytest.raises(PermissionDeniedError):
        WorkSessionService(actor=employee).end_session(session.id)


def test_supervisor_can_end_someone_elses_session(supervisor, employee, masters):
    session = WorkSession.objects.create(
        emp_id=employee.emp_id, project="Test Project",
        start_time=now_ist() - timedelta(minutes=5),
        is_started=SessionState.RUNNING,
    )

    finished = WorkSessionService(actor=supervisor).end_session(session.id)
    assert finished.is_started == SessionState.COMPLETED


# ── the IST clock ────────────────────────────────────────────

def test_now_ist_is_timezone_aware_and_in_ist():
    value = now_ist()

    assert value.tzinfo is not None
    assert value.utcoffset() == timedelta(hours=5, minutes=30)


def test_today_ist_matches_the_ist_calendar_day():
    """Between 18:30 and 00:00 UTC, utcnow().date() and today_ist() disagree —
    and that window is exactly when the evening shift works."""
    assert today_ist() == now_ist().astimezone(IST).date()


def test_elapsed_seconds_never_returns_a_negative():
    """Clock skew or a bad legacy row must not poison an average."""
    from core.timezone import elapsed_seconds

    start = now_ist()
    end = start - timedelta(hours=1)

    assert elapsed_seconds(start, end) == 0.0
