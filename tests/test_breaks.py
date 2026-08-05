"""Break rules: server-owned allowances and the one-open-break guarantee."""

from __future__ import annotations

import pytest

from apps.breaks.constants import BREAK_ALLOWANCES
from apps.breaks.models import BreakTime
from apps.breaks.services import BreakService
from core.exceptions import ConflictError, ValidationError

pytestmark = pytest.mark.django_db


def test_allowance_comes_from_the_server(employee):
    brk = BreakService(actor=employee).start_break("Tea break 1")

    assert brk.allotted_time == BREAK_ALLOWANCES["Tea break 1"]


def test_client_cannot_set_its_own_allowance(as_employee):
    """The serializer has no allotted_time field, so the extra key is dropped
    rather than honoured."""
    response = as_employee.post(
        "/api/v1/breaks/", {"break_type": "Tea break 1", "allotted_time": 99999}
    )

    assert response.status_code == 201
    assert response.data["data"]["allotted_time"] == BREAK_ALLOWANCES["Tea break 1"]


def test_unknown_break_type_is_rejected(employee):
    with pytest.raises(ValidationError):
        BreakService(actor=employee).start_break("Four hour nap")


def test_only_one_break_may_be_open(employee):
    service = BreakService(actor=employee)
    service.start_break("Tea break 1")

    with pytest.raises(ConflictError):
        service.start_break("Meal break")


def test_a_non_repeatable_break_cannot_be_taken_twice_in_a_day(employee):
    service = BreakService(actor=employee)

    service.start_break("Tea break 1")
    service.end_break()

    with pytest.raises(ConflictError):
        service.start_break("Tea break 1")


def test_a_repeatable_break_can_be_taken_again(employee):
    service = BreakService(actor=employee)

    service.start_break("Rest room")
    service.end_break()
    second = service.start_break("Rest room")

    assert second.is_open


def test_ending_a_break_records_the_duration(employee):
    service = BreakService(actor=employee)
    service.start_break("Tea break 1")

    finished = service.end_break()

    assert finished.end_time is not None
    assert finished.total_time is not None
    assert finished.total_time >= 0


def test_ending_a_break_that_is_not_running_is_a_404(employee):
    from core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        BreakService(actor=employee).end_break()


def test_overrun_is_flagged(employee):
    from datetime import timedelta

    from core.timezone import now_ist

    service = BreakService(actor=employee)
    brk = service.start_break("Tea break 1")

    # Backdate the start so the break is well past its five-minute allowance.
    BreakTime.objects.filter(pk=brk.pk).update(
        start_time=now_ist() - timedelta(minutes=30)
    )

    finished = service.end_break()
    assert finished.is_overrun is True


def test_break_types_endpoint_reports_allowances(as_employee):
    response = as_employee.get("/api/v1/breaks/types/")

    assert response.status_code == 200
    types = {row["break_type"]: row for row in response.data["data"]}
    assert types["Tea break 1"]["allotted_seconds"] == BREAK_ALLOWANCES["Tea break 1"]


def test_employee_cannot_force_end_another_persons_break(as_employee, other_employee):
    brk = BreakService(actor=other_employee).start_break("Tea break 1")

    response = as_employee.post(f"/api/v1/breaks/{brk.id}/force-end/")
    assert response.status_code == 403


def test_supervisor_can_force_end_a_break(as_supervisor, employee):
    brk = BreakService(actor=employee).start_break("Tea break 1")

    response = as_supervisor.post(f"/api/v1/breaks/{brk.id}/force-end/")

    assert response.status_code == 200
    brk.refresh_from_db()
    assert brk.end_time is not None
