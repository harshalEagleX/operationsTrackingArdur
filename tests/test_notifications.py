"""The in-app notification inbox.

Per the product requirement that notifications keep working while chat stays
on hold: these tests exercise the real delivery path end to end — the
registry, preference filtering, the transaction.on_commit delivery hook, and
the inbox/preferences endpoints — and confirm chat's two notification types
exist in the registry but are inert (apps.chat is not an installed app, so
nothing can trigger them).
"""

from __future__ import annotations

import pytest

from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.services import NotificationService

pytestmark = pytest.mark.django_db


# ── NotificationService.notify ───────────────────────────────

def test_notify_creates_one_row_per_recipient(employee, other_employee):
    created = NotificationService().notify(
        recipients=[employee.emp_id, other_employee.emp_id],
        notif_type="work.target_met",
        context={"project": "Test Project"},
    )

    assert len(created) == 2
    assert Notification.objects.filter(notif_type="work.target_met").count() == 2


def test_notify_deduplicates_recipients(employee):
    created = NotificationService().notify(
        recipients=[employee.emp_id, employee.emp_id],
        notif_type="work.target_met",
        context={"project": "Test Project"},
    )
    assert len(created) == 1


def test_notify_never_tells_the_actor_about_their_own_action(employee, supervisor):
    created = NotificationService(actor=supervisor).notify(
        recipients=[employee.emp_id, supervisor.emp_id],
        notif_type="allocation.assigned",
        context={"task_id": "A-1", "project": "P", "quantity": 5},
    )

    recipients = {n.recipient_emp_id for n in created}
    assert recipients == {employee.emp_id}


def test_notify_renders_the_title_from_context(employee):
    [notification] = NotificationService().notify(
        recipients=[employee.emp_id],
        notif_type="allocation.assigned",
        context={"task_id": "ALLOC-42", "project": "Test Project", "quantity": 10},
    )
    assert notification.title == "New order ALLOC-42 assigned to you"


def test_notify_tolerates_a_missing_context_key(employee):
    """render_title catches KeyError so a missing template value degrades to
    the raw template instead of turning a business action into a 500."""
    [notification] = NotificationService().notify(
        recipients=[employee.emp_id], notif_type="allocation.assigned", context={},
    )
    assert notification.title  # did not raise


def test_notify_with_no_recipients_left_after_dedup_creates_nothing(employee):
    created = NotificationService(actor=employee).notify(
        recipients=[employee.emp_id], notif_type="work.target_met", context={},
    )
    assert created == []


def test_notify_respects_an_opted_out_preference(employee):
    NotificationPreference.objects.create(
        emp_id=employee.emp_id, notif_type="work.target_met", in_app=False, email=False,
    )

    created = NotificationService().notify(
        recipients=[employee.emp_id], notif_type="work.target_met", context={},
    )
    assert created == []


def test_notify_rejects_an_unknown_type(employee):
    with pytest.raises(KeyError):
        NotificationService().notify(recipients=[employee.emp_id], notif_type="not.a.real.type")


def test_notify_is_delivered_over_the_socket_on_commit(django_capture_on_commit_callbacks, employee):
    """The realtime push (not just the DB row) is deferred to on_commit —
    confirms it actually fires rather than silently no-op-ing."""
    from core.events import publish  # noqa: F401  (imported for readability of the assertion below)

    with django_capture_on_commit_callbacks(execute=True):
        NotificationService().notify(
            recipients=[employee.emp_id], notif_type="work.target_met", context={},
        )

    # publish() writes a durable outbox row before fanning out — that row is
    # the socket-independent proof the push was attempted.
    from apps.realtime.models import OutboxEvent

    assert OutboxEvent.objects.filter(
        event_type="notification.created", topic=f"user.{employee.emp_id}"
    ).exists()


# ── mark_read / unread_count ─────────────────────────────────

def test_unread_count_starts_at_zero(employee):
    assert NotificationService.unread_count(employee.emp_id) == 0


def test_mark_read_without_ids_clears_everything(employee):
    NotificationService().notify(recipients=[employee.emp_id], notif_type="work.target_met", context={})
    NotificationService().notify(recipients=[employee.emp_id], notif_type="report.ready", context={})

    count = NotificationService(actor=employee).mark_read(employee.emp_id)

    assert count == 2
    assert NotificationService.unread_count(employee.emp_id) == 0


def test_mark_read_with_ids_only_clears_those(employee):
    [a] = NotificationService().notify(recipients=[employee.emp_id], notif_type="work.target_met", context={})
    [b] = NotificationService().notify(recipients=[employee.emp_id], notif_type="report.ready", context={})

    NotificationService(actor=employee).mark_read(employee.emp_id, [a.id])

    assert Notification.objects.get(pk=a.id).is_read is True
    assert Notification.objects.get(pk=b.id).is_read is False


# ── set_preference ────────────────────────────────────────────

def test_a_user_can_turn_off_a_configurable_notification_type(employee):
    pref = NotificationService(actor=employee).set_preference(
        employee.emp_id, "work.target_met", in_app=False, email=False
    )
    assert pref.in_app is False


def test_a_non_configurable_type_cannot_be_turned_off(employee):
    from core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        NotificationService(actor=employee).set_preference(
            employee.emp_id, "allocation.sla_breach", in_app=False, email=False
        )


# ── HTTP: inbox and preferences ──────────────────────────────

def test_inbox_is_scoped_to_the_caller(as_employee, employee, other_employee):
    [mine] = NotificationService().notify(
        recipients=[employee.emp_id], notif_type="work.target_met", context={}
    )
    NotificationService().notify(
        recipients=[other_employee.emp_id], notif_type="work.target_met", context={}
    )

    response = as_employee.get("/api/v1/notifications/")
    ids = [row["id"] for row in response.data["data"]]

    assert ids == [mine.id]


def test_inbox_meta_reports_unread_count(as_employee, employee):
    NotificationService().notify(recipients=[employee.emp_id], notif_type="work.target_met", context={})
    NotificationService().notify(recipients=[employee.emp_id], notif_type="report.ready", context={})

    response = as_employee.get("/api/v1/notifications/")
    assert response.data["meta"]["unread_count"] == 2


def test_unread_only_filter(as_employee, employee):
    [a] = NotificationService().notify(recipients=[employee.emp_id], notif_type="work.target_met", context={})
    NotificationService(actor=employee).mark_read(employee.emp_id, [a.id])
    NotificationService().notify(recipients=[employee.emp_id], notif_type="report.ready", context={})

    response = as_employee.get("/api/v1/notifications/", {"unread": "true"})
    types = [row["notif_type"] for row in response.data["data"]]

    assert types == ["report.ready"]


def test_unread_count_endpoint(as_employee, employee):
    NotificationService().notify(recipients=[employee.emp_id], notif_type="work.target_met", context={})

    response = as_employee.get("/api/v1/notifications/unread-count/")
    assert response.data["data"]["unread_count"] == 1


def test_mark_read_endpoint(as_employee, employee):
    NotificationService().notify(recipients=[employee.emp_id], notif_type="work.target_met", context={})

    response = as_employee.post("/api/v1/notifications/read/", {"ids": []})
    assert response.status_code == 200
    assert response.data["data"]["marked"] == 1


def test_preferences_get_shows_registry_defaults_when_nothing_stored(as_employee):
    response = as_employee.get("/api/v1/notifications/preferences/")

    rows = {row["notif_type"]: row for row in response.data["data"]}
    assert rows["work.target_met"]["in_app"] is True
    # Types reserved for chat are configurable in the registry but cannot
    # actually fire — apps.chat is not installed.
    assert "chat.mention" in rows


def test_preferences_post_persists_an_override(as_employee, employee):
    response = as_employee.post(
        "/api/v1/notifications/preferences/",
        {"notif_type": "work.target_met", "in_app": False, "email": False},
    )

    assert response.status_code == 200
    assert NotificationPreference.objects.get(
        emp_id=employee.emp_id, notif_type="work.target_met"
    ).in_app is False


def test_notifications_endpoints_reject_anonymous_requests(api):
    assert api.get("/api/v1/notifications/").status_code in (401, 403)
    assert api.get("/api/v1/notifications/preferences/").status_code in (401, 403)


# ── chat stays on hold ────────────────────────────────────────

def test_chat_app_is_not_installed():
    from django.apps import apps

    assert not apps.is_installed("apps.chat")


def test_chat_feature_flag_is_off():
    from django.conf import settings

    assert settings.FEATURE_CHAT is False


def test_chat_notification_types_exist_in_the_registry_but_cannot_be_triggered():
    """The registry entries are deliberately present (see registry.py 'reserved
    for apps.chat') so wiring chat in later is additive. Nothing in an
    installed app calls notify() with them today — a regression here would
    mean chat got wired in without the feature-flag/access-control review
    that turning it on is supposed to require."""
    import pathlib
    import re

    from apps.notifications.registry import get

    assert get("chat.mention").key == "chat.mention"
    assert get("chat.message").key == "chat.message"

    apps_dir = pathlib.Path(__file__).resolve().parent.parent / "apps"
    call_site = re.compile(r"notify\([^)]*chat\.(mention|message)")

    offenders = [
        path
        for path in apps_dir.rglob("*.py")
        if "apps/chat/" not in path.as_posix() and call_site.search(path.read_text())
    ]
    assert offenders == []
