"""Presence: derived status, not declared.

The precedence chain (on_break > working > busy(manual) > online > idle >
offline) is the whole point of this module — a manual "online" must never
outrank an actual open break.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache

from apps.presence.models import PresenceState, PresenceStatus, StatusSource
from apps.presence.services import PresenceService
from core.timezone import now_ist

pytestmark = pytest.mark.django_db

# Cache is cleared per-test by the autouse fixture in tests/conftest.py.


# ── precedence ────────────────────────────────────────────────

def test_default_status_is_offline(employee):
    assert PresenceService().recompute(employee.emp_id) == PresenceStatus.OFFLINE


def test_a_socket_makes_you_online(employee):
    service = PresenceService()
    service.connect(employee.emp_id)
    assert service.recompute(employee.emp_id) == PresenceStatus.ONLINE


def test_an_open_break_outranks_everything(employee):
    from apps.breaks.models import BreakTime

    service = PresenceService()
    service.connect(employee.emp_id)
    service.set_manual(employee.emp_id, PresenceStatus.BUSY)

    BreakTime.objects.create(user_id=employee.emp_id, break_type="Tea break 1")

    assert service.recompute(employee.emp_id) == PresenceStatus.ON_BREAK


def test_an_open_work_session_outranks_manual_status(employee, masters):
    from apps.tracking.models import SessionState, WorkSession

    service = PresenceService()
    service.set_manual(employee.emp_id, PresenceStatus.BUSY)
    WorkSession.objects.create(
        emp_id=employee.emp_id, project="Test Project", is_started=SessionState.RUNNING,
        is_paused=False,
    )

    assert service.recompute(employee.emp_id) == PresenceStatus.WORKING


def test_a_paused_session_does_not_count_as_working(employee, masters):
    """active_now() filters is_paused=False — a paused session is not
    'currently working' for presence purposes."""
    from apps.tracking.models import SessionState, WorkSession

    WorkSession.objects.create(
        emp_id=employee.emp_id, project="Test Project", is_started=SessionState.RUNNING,
        is_paused=True,
    )

    assert PresenceService().recompute(employee.emp_id) == PresenceStatus.OFFLINE


def test_manual_status_requires_an_active_connection(employee):
    """A 'busy' badge set from a tab that has since disconnected must not
    outlive the socket — it degrades to offline, not a stale busy forever."""
    service = PresenceService()
    service.set_manual(employee.emp_id, PresenceStatus.BUSY)
    # set_manual's own recompute() call added a connection implicitly via
    # nothing — force disconnect to simulate the tab having gone away.
    service.force_offline(employee.emp_id)

    assert service.recompute(employee.emp_id) == PresenceStatus.OFFLINE


def test_idle_after_the_grace_period(employee):
    service = PresenceService()
    service.connect(employee.emp_id)

    PresenceState.objects.filter(emp_id=employee.emp_id).update(
        last_heartbeat_at=now_ist() - timedelta(minutes=10)
    )

    assert service.recompute(employee.emp_id) == PresenceStatus.IDLE


# ── connection counting ──────────────────────────────────────

def test_multiple_tabs_do_not_go_offline_until_the_last_disconnects(employee):
    service = PresenceService()
    service.connect(employee.emp_id)
    service.connect(employee.emp_id)  # second tab

    service.disconnect(employee.emp_id)  # first tab closes
    assert service.recompute(employee.emp_id) == PresenceStatus.ONLINE

    service.disconnect(employee.emp_id)  # last tab closes
    assert service.recompute(employee.emp_id) == PresenceStatus.OFFLINE


def test_connection_count_never_goes_negative(employee):
    service = PresenceService()
    service.disconnect(employee.emp_id)  # disconnect with no prior connect
    assert service._connection_count(employee.emp_id) == 0


# ── broadcast-only-on-change ──────────────────────────────────

def test_recompute_only_broadcasts_on_a_real_transition(employee):
    """Presence broadcasts are durable=False on purpose ('replaying a stale
    status is worse than none' — see PresenceService._store), so they never
    hit the outbox table; assert on publish() itself instead."""
    from unittest.mock import patch

    with patch("apps.presence.services.publish") as published:
        service = PresenceService()
        service.connect(employee.emp_id)  # offline -> online: one broadcast
        assert published.call_count == 1
        assert published.call_args.kwargs["event"] == "presence.changed"
        assert published.call_args.kwargs["durable"] is False

        service.heartbeat(employee.emp_id)  # no status change: no broadcast
        assert published.call_count == 1


# ── reads ────────────────────────────────────────────────────

def test_get_returns_offline_shape_for_an_unknown_employee():
    result = PresenceService().get("NOBODY99")
    assert result == {"emp_id": "NOBODY99", "status": PresenceStatus.OFFLINE, "source": "socket"}


def test_get_prefers_the_cache_over_the_database(employee):
    service = PresenceService()
    service.connect(employee.emp_id)

    # Mutate the DB row directly without going through the service — get()
    # should still answer from the cached, more current value.
    PresenceState.objects.filter(emp_id=employee.emp_id).update(status=PresenceStatus.OFFLINE)

    assert service.get(employee.emp_id)["status"] == PresenceStatus.ONLINE


def test_roster_includes_every_active_employee(employee, other_employee):
    PresenceService().connect(employee.emp_id)

    roster = PresenceService().roster()
    by_id = {row["emp_id"]: row for row in roster}

    assert by_id[employee.emp_id]["status"] == PresenceStatus.ONLINE
    assert by_id[other_employee.emp_id]["status"] == PresenceStatus.OFFLINE


def test_roster_excludes_inactive_employees(employee):
    from apps.accounts.models import Employee

    Employee.objects.filter(employee_id=employee.emp_id).update(status="inactive")

    roster = PresenceService().roster()
    assert employee.emp_id not in {row["emp_id"] for row in roster}


# ── HTTP ─────────────────────────────────────────────────────

def test_roster_endpoint(as_employee, employee):
    response = as_employee.get("/api/v1/presence/")
    assert response.status_code == 200
    assert isinstance(response.data["data"], list)


def test_me_get_endpoint(as_employee, employee):
    response = as_employee.get("/api/v1/presence/me/")
    assert response.status_code == 200
    assert response.data["data"]["emp_id"] == employee.emp_id


def test_me_post_sets_manual_status(as_employee, employee):
    """A manual status only sticks with a live connection — see
    test_manual_status_requires_an_active_connection. In the real app the
    websocket connects before the UI offers a status picker; simulate that."""
    PresenceService().connect(employee.emp_id)

    response = as_employee.post("/api/v1/presence/me/", {"status": "busy"})
    assert response.status_code == 200
    assert response.data["data"]["status"] == "busy"


def test_me_post_rejects_working_and_on_break_as_manual_choices(as_employee):
    """Those are derived, not declared — SetStatusSerializer's choices
    deliberately exclude them."""
    response = as_employee.post("/api/v1/presence/me/", {"status": "working"})
    assert response.status_code == 400


def test_detail_endpoint_for_another_employee(as_supervisor, employee):
    response = as_supervisor.get(f"/api/v1/presence/{employee.emp_id}/")
    assert response.status_code == 200
    assert response.data["data"]["emp_id"] == employee.emp_id


def test_presence_endpoints_reject_anonymous_requests(api):
    assert api.get("/api/v1/presence/").status_code in (401, 403)
    assert api.get("/api/v1/presence/me/").status_code in (401, 403)


# ── background tasks ─────────────────────────────────────────

def test_reap_stale_presence_offlines_a_dead_socket_whose_cache_key_expired(employee):
    from apps.presence.tasks import reap_stale_presence

    service = PresenceService()
    service.connect(employee.emp_id)

    # Simulate the Redis TTL having already expired (the durable row is
    # behind reality) but the row itself looks stale.
    cache.delete(f"presence:state:{employee.emp_id}")
    PresenceState.objects.filter(emp_id=employee.emp_id).update(
        status=PresenceStatus.ONLINE, last_seen_at=now_ist() - timedelta(minutes=5)
    )

    result = reap_stale_presence()

    assert result["reaped"] == 1
    assert PresenceState.objects.get(emp_id=employee.emp_id).status == PresenceStatus.OFFLINE


def test_reap_stale_presence_leaves_a_live_socket_alone(employee):
    """If the cache key is still alive, the user is genuinely connected —
    the durable row is just behind, not stale."""
    from apps.presence.tasks import reap_stale_presence

    service = PresenceService()
    service.connect(employee.emp_id)
    PresenceState.objects.filter(emp_id=employee.emp_id).update(
        last_seen_at=now_ist() - timedelta(minutes=5)
    )

    result = reap_stale_presence()

    assert result["reaped"] == 0


def test_refresh_derived_presence_reconciles_active_workers(employee, masters):
    from apps.tracking.models import SessionState, WorkSession

    from apps.presence.tasks import refresh_derived_presence

    WorkSession.objects.create(
        emp_id=employee.emp_id, project="Test Project", is_started=SessionState.RUNNING,
    )

    result = refresh_derived_presence()

    assert result["recomputed"] >= 1
    assert PresenceState.objects.get(emp_id=employee.emp_id).status == PresenceStatus.WORKING


# ── source tagging ───────────────────────────────────────────

def test_set_status_records_the_source(employee):
    PresenceService().set_status(employee.emp_id, PresenceStatus.WORKING, StatusSource.WORK_SESSION)
    state = PresenceState.objects.get(emp_id=employee.emp_id)
    assert state.status_source == StatusSource.WORK_SESSION
