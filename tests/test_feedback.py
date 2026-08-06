"""Quality feedback: the read rule (about-me or written-by-me), and the
create/acknowledge/edit lifecycle.

test_permissions.py already covers the cross-employee read boundary; this
file covers the service/serializer rules and the rest of the HTTP surface.
"""

from __future__ import annotations

import pytest

from apps.feedback.models import Feedback
from apps.feedback.services import FeedbackService
from core.exceptions import ConflictError, PermissionDeniedError, ValidationError

pytestmark = pytest.mark.django_db


# ── FeedbackService.create ────────────────────────────────────

def test_only_a_supervisor_can_create_feedback(employee, other_employee):
    with pytest.raises(PermissionDeniedError):
        FeedbackService(actor=employee).create({"emp_id": other_employee.emp_id, "subject": "x"})


def test_a_supervisor_cannot_record_feedback_about_themselves(supervisor):
    with pytest.raises(ValidationError):
        FeedbackService(actor=supervisor).create({"emp_id": supervisor.emp_id, "subject": "x"})


def test_error_count_cannot_exceed_sample_size(supervisor, employee):
    with pytest.raises(ValidationError):
        FeedbackService(actor=supervisor).create(
            {"emp_id": employee.emp_id, "subject": "x", "error_count": 10, "sample_size": 5}
        )


def test_create_stamps_the_author(supervisor, employee):
    feedback = FeedbackService(actor=supervisor).create(
        {"emp_id": employee.emp_id, "subject": "Great work"}
    )
    assert feedback.created_by == supervisor.emp_id
    assert feedback.created_by_name == supervisor.display_name


def test_create_notifies_the_subject(django_capture_on_commit_callbacks, supervisor, employee):
    from apps.notifications.models import Notification

    with django_capture_on_commit_callbacks(execute=True):
        FeedbackService(actor=supervisor).create({"emp_id": employee.emp_id, "subject": "x"})

    assert Notification.objects.filter(
        recipient_emp_id=employee.emp_id, notif_type="feedback.received"
    ).exists()


# ── acknowledge ────────────────────────────────────────────────

def test_only_the_subject_can_acknowledge(employee, other_employee, supervisor):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)

    with pytest.raises(PermissionDeniedError):
        FeedbackService(actor=other_employee).acknowledge(feedback.id)


def test_acknowledge_records_the_response(employee, supervisor):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)

    acknowledged = FeedbackService(actor=employee).acknowledge(feedback.id, "Understood, thanks.")

    assert acknowledged.is_acknowledged is True
    assert acknowledged.response == "Understood, thanks."


def test_cannot_acknowledge_twice(employee, supervisor):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)
    FeedbackService(actor=employee).acknowledge(feedback.id)

    with pytest.raises(ConflictError):
        FeedbackService(actor=employee).acknowledge(feedback.id)


def test_acknowledging_missing_feedback_is_not_found(employee):
    from core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        FeedbackService(actor=employee).acknowledge(999999)


def test_acknowledge_notifies_the_author(django_capture_on_commit_callbacks, employee, supervisor):
    from apps.realtime.models import OutboxEvent

    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)

    with django_capture_on_commit_callbacks(execute=True):
        FeedbackService(actor=employee).acknowledge(feedback.id)

    assert OutboxEvent.objects.filter(
        topic=f"user.{supervisor.emp_id}", event_type="feedback.acknowledged"
    ).exists()


# ── update ────────────────────────────────────────────────────

def test_only_the_author_can_edit(employee, supervisor, admin):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)

    other_supervisor_service = FeedbackService(actor=admin)
    updated = other_supervisor_service.update(feedback, {"subject": "edited by admin"})
    assert updated.subject == "edited by admin"  # admin override allowed


def test_a_non_author_non_admin_cannot_edit(employee, supervisor, other_employee):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)

    from apps.accounts.models import Employee, User

    Employee.objects.create(employee_id="SUP002", name="Other Sup", role="supervisor", status="active")
    other_sup = User.objects.create_user(emp_id="SUP002", password="x", name="Other Sup")

    with pytest.raises(PermissionDeniedError):
        FeedbackService(actor=other_sup).update(feedback, {"subject": "hijacked"})


def test_acknowledged_feedback_cannot_be_edited_by_the_author(employee, supervisor):
    feedback = Feedback.objects.create(
        emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id,
    )
    FeedbackService(actor=employee).acknowledge(feedback.id)
    feedback.refresh_from_db()  # acknowledge() wrote through a separate fetch

    with pytest.raises(ConflictError):
        FeedbackService(actor=supervisor).update(feedback, {"subject": "too late"})


def test_admin_can_still_edit_acknowledged_feedback(employee, supervisor, admin):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)
    FeedbackService(actor=employee).acknowledge(feedback.id)

    updated = FeedbackService(actor=admin).update(feedback, {"subject": "admin override"})
    assert updated.subject == "admin override"


def test_update_cannot_reassign_the_subject(employee, other_employee, supervisor):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)

    FeedbackService(actor=supervisor).update(feedback, {"emp_id": other_employee.emp_id})

    feedback.refresh_from_db()
    assert feedback.emp_id == employee.emp_id  # unchanged


# ── delete ────────────────────────────────────────────────────

def test_only_an_admin_can_delete_feedback(employee, supervisor):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)
    with pytest.raises(PermissionDeniedError):
        FeedbackService(actor=supervisor).delete(feedback)


def test_admin_can_delete_feedback(employee, supervisor, admin):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)
    FeedbackService(actor=admin).delete(feedback)
    assert not Feedback.objects.filter(pk=feedback.pk).exists()


# ── can_read ──────────────────────────────────────────────────

def test_can_read_true_for_supervisor_subject_and_author(employee, supervisor, admin):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)

    assert FeedbackService(actor=supervisor).can_read(feedback) is True
    assert FeedbackService(actor=employee).can_read(feedback) is True
    assert FeedbackService(actor=admin).can_read(feedback) is True  # admin is a supervisor


def test_can_read_false_for_an_unrelated_employee(employee, other_employee, supervisor):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)
    assert FeedbackService(actor=other_employee).can_read(feedback) is False


def test_can_read_false_with_no_actor():
    feedback = Feedback(emp_id="E1", subject="x")
    assert FeedbackService(actor=None).can_read(feedback) is False


# ── HTTP ─────────────────────────────────────────────────────

def test_create_over_http(as_supervisor, employee):
    response = as_supervisor.post(
        "/api/v1/feedback/", {"emp_id": employee.emp_id, "subject": "Nice batch"}
    )
    assert response.status_code == 201
    assert response.data["data"]["created_by_name"]


def test_create_rejects_an_unknown_employee(as_supervisor):
    response = as_supervisor.post(
        "/api/v1/feedback/", {"emp_id": "NOSUCHEMP", "subject": "x"}
    )
    assert response.status_code == 400


def test_acknowledge_over_http(as_employee, employee, supervisor):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)
    response = as_employee.post(
        f"/api/v1/feedback/{feedback.id}/acknowledge/", {"response": "Got it"}
    )
    assert response.status_code == 200
    assert response.data["data"]["is_acknowledged"] is True


def test_mine_endpoint_returns_only_the_callers_feedback(as_employee, employee, other_employee, supervisor):
    mine = Feedback.objects.create(emp_id=employee.emp_id, subject="mine", created_by=supervisor.emp_id)
    Feedback.objects.create(emp_id=other_employee.emp_id, subject="not mine", created_by=supervisor.emp_id)

    response = as_employee.get("/api/v1/feedback/mine/")
    ids = [row["id"] for row in response.data["data"]]

    assert ids == [mine.id]


def test_update_over_http(as_supervisor, employee, supervisor):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)
    response = as_supervisor.patch(f"/api/v1/feedback/{feedback.id}/", {"subject": "revised"})

    assert response.status_code == 200
    assert response.data["data"]["subject"] == "revised"


def test_delete_over_http_requires_admin(as_supervisor, employee, supervisor):
    feedback = Feedback.objects.create(emp_id=employee.emp_id, subject="x", created_by=supervisor.emp_id)
    response = as_supervisor.delete(f"/api/v1/feedback/{feedback.id}/")
    assert response.status_code == 403


def test_filter_by_severity_and_type(as_supervisor, employee, supervisor):
    Feedback.objects.create(
        emp_id=employee.emp_id, subject="critical one", created_by=supervisor.emp_id, severity="critical",
    )
    Feedback.objects.create(
        emp_id=employee.emp_id, subject="minor one", created_by=supervisor.emp_id, severity="minor",
    )

    response = as_supervisor.get("/api/v1/feedback/", {"severity": "critical"})
    subjects = [row["subject"] for row in response.data["data"]]
    assert subjects == ["critical one"]


def test_unacknowledged_filter(as_supervisor, employee, supervisor):
    acked = Feedback.objects.create(
        emp_id=employee.emp_id, subject="acked", created_by=supervisor.emp_id,
    )
    FeedbackService(actor=employee).acknowledge(acked.id)
    Feedback.objects.create(emp_id=employee.emp_id, subject="pending", created_by=supervisor.emp_id)

    response = as_supervisor.get("/api/v1/feedback/", {"unacknowledged": "true"})
    subjects = [row["subject"] for row in response.data["data"]]
    assert subjects == ["pending"]


def test_feedback_endpoints_reject_anonymous_requests(api):
    assert api.get("/api/v1/feedback/").status_code in (401, 403)
