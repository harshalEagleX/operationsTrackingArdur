"""The realtime gateway: wire protocol, group naming/authorisation, tickets,
the durable outbox, and the WebSocket consumer itself.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from channels.testing import WebsocketCommunicator
from django.core.cache import cache

from apps.realtime.groups import (
    can_subscribe,
    conversation_group,
    default_groups_for,
    is_valid_group,
    presence_group,
    project_group,
    role_group,
    user_group,
)
from apps.realtime.models import OutboxEvent, WebSocketTicket
from apps.realtime.protocol import (
    ClientOp,
    CloseCode,
    ServerOp,
    envelope,
    error_frame,
    is_valid_client_frame,
    pong_frame,
    ready_frame,
)
from apps.realtime.tickets import TicketService, purge_expired_tickets
from opstracking.asgi import application

pytestmark = pytest.mark.django_db


# ── protocol.py ───────────────────────────────────────────────

def test_envelope_always_carries_version_and_op_and_timestamp():
    frame = envelope("event", topic="user.E1", event_type="ping", data={"x": 1}, seq=5)
    assert frame["v"] == 1
    assert frame["op"] == "event"
    assert frame["topic"] == "user.E1"
    assert frame["type"] == "ping"
    assert frame["seq"] == 5
    assert frame["data"] == {"x": 1}
    assert "ts" in frame


def test_envelope_omits_unset_optional_fields():
    frame = envelope("pong")
    assert set(frame) == {"v", "op", "ts"}


def test_error_frame_shape():
    frame = error_frame("forbidden", "no")
    assert frame["op"] == ServerOp.ERROR
    assert frame["data"] == {"code": "forbidden", "message": "no"}


def test_pong_frame_shape():
    assert pong_frame()["op"] == ServerOp.PONG


def test_ready_frame_carries_the_handshake_payload():
    frame = ready_frame(emp_id="E1", cursors={"user.E1": 5}, heartbeat_interval=20, groups=["a", "b"])
    assert frame["data"]["emp_id"] == "E1"
    assert frame["data"]["topics"] == ["a", "b"]
    assert frame["data"]["protocol_version"] == 1


@pytest.mark.parametrize(
    "frame",
    [
        "not a dict",
        {},  # missing op
        {"op": "delete_everything"},  # unknown op
        {"op": "ping", "v": 99},  # wrong version
    ],
)
def test_is_valid_client_frame_rejects_bad_input(frame):
    ok, reason = is_valid_client_frame(frame)
    assert ok is False
    assert reason


def test_is_valid_client_frame_accepts_every_declared_client_op():
    for op in ClientOp.ALL:
        ok, _ = is_valid_client_frame({"op": op})
        assert ok is True


# ── groups.py ─────────────────────────────────────────────────

def test_user_group_sanitises_the_emp_id():
    # Each disallowed character is replaced individually, not collapsed —
    # "E 1" has one, "/.." has three, trailing "/" one more: 1+3+1 = 5 dashes.
    assert user_group("E 1/../etc") == "user.E-1----etc"


def test_presence_group_is_a_constant():
    assert presence_group() == "presence.all"


def test_project_and_role_group_naming():
    assert project_group("Northwind Records") == "project.Northwind-Records"
    assert role_group("supervisor") == "role.supervisor"


def test_conversation_group_is_reserved_for_chat():
    assert conversation_group(42).startswith("chat.conv.")


def test_is_valid_group_enforces_the_channels_charset():
    assert is_valid_group("user.E1042") is True
    assert is_valid_group("") is False
    assert is_valid_group("has a space") is False
    assert is_valid_group("x" * 100) is False


def test_default_groups_for_includes_project_when_the_employee_has_one(employee):
    from apps.accounts.models import Employee

    Employee.objects.filter(employee_id=employee.emp_id).update(project="Northwind Records")
    fresh = _reload_user(employee)

    groups = default_groups_for(fresh)
    assert user_group(employee.emp_id) in groups
    assert presence_group() in groups
    assert role_group("employee") in groups
    assert project_group("Northwind Records") in groups


def test_default_groups_for_skips_project_when_the_employee_has_none(employee):
    from apps.accounts.models import Employee

    # The `employee` fixture sets project="Test Project" by default — clear
    # it to exercise the "no project" branch.
    Employee.objects.filter(employee_id=employee.emp_id).update(project="")
    fresh = _reload_user(employee)

    groups = default_groups_for(fresh)
    assert not any(g.startswith("project.") for g in groups)


def _reload_user(user):
    from apps.accounts.models import User

    return User.objects.get(pk=user.pk)


# ── can_subscribe: the authorisation boundary ─────────────────

def test_can_subscribe_to_your_own_topic(employee):
    assert can_subscribe(employee, user_group(employee.emp_id)) is True


def test_cannot_subscribe_to_someone_elses_topic(employee, other_employee):
    assert can_subscribe(employee, user_group(other_employee.emp_id)) is False


def test_supervisor_still_cannot_subscribe_to_someone_elses_user_topic(supervisor, employee):
    """Nobody rides someone else's socket stream — not even a supervisor."""
    assert can_subscribe(supervisor, user_group(employee.emp_id)) is False


def test_everyone_can_subscribe_to_presence(employee):
    assert can_subscribe(employee, presence_group()) is True


def test_can_subscribe_to_your_own_role_topic(employee):
    assert can_subscribe(employee, role_group("employee")) is True


def test_supervisor_can_subscribe_to_any_project(supervisor):
    assert can_subscribe(supervisor, project_group("Some Project")) is True


def test_employee_can_subscribe_only_to_their_own_project(employee):
    from apps.accounts.models import Employee

    Employee.objects.filter(employee_id=employee.emp_id).update(project="Mine")
    fresh = _reload_user(employee)

    assert can_subscribe(fresh, project_group("Mine")) is True
    assert can_subscribe(fresh, project_group("Someone Elses")) is False


def test_chat_topics_are_always_refused(employee):
    assert can_subscribe(employee, "chat.conv.1") is False


def test_can_subscribe_refuses_an_invalid_topic_name(employee):
    assert can_subscribe(employee, "not a valid group!") is False


def test_can_subscribe_refuses_anonymous_and_unauthenticated_users():
    from django.contrib.auth.models import AnonymousUser

    assert can_subscribe(None, presence_group()) is False
    assert can_subscribe(AnonymousUser(), presence_group()) is False


# ── OutboxEvent / WebSocketTicket models ─────────────────────

def test_outbox_event_to_frame():
    event = OutboxEvent.objects.create(
        topic="user.E1", audience="user.E1", event_type="ping", payload={"x": 1}
    )
    frame = event.to_frame()
    assert frame["op"] == ServerOp.EVENT
    assert frame["seq"] == event.id
    assert frame["data"] == {"x": 1}


def test_websocket_ticket_is_usable_before_expiry_and_redemption():
    from core.timezone import now_ist

    ticket = WebSocketTicket.objects.create(
        token="abc", emp_id="E1", expires_at=now_ist() + timedelta(seconds=60)
    )
    assert ticket.is_usable is True


def test_websocket_ticket_is_not_usable_once_expired():
    from core.timezone import now_ist

    ticket = WebSocketTicket.objects.create(
        token="abc", emp_id="E1", expires_at=now_ist() - timedelta(seconds=1)
    )
    assert ticket.is_usable is False


def test_websocket_ticket_is_not_usable_once_redeemed():
    from core.timezone import now_ist

    ticket = WebSocketTicket.objects.create(
        token="abc", emp_id="E1", expires_at=now_ist() + timedelta(seconds=60),
        redeemed_at=now_ist(),
    )
    assert ticket.is_usable is False


# ── TicketService ─────────────────────────────────────────────

def test_issue_returns_a_usable_ticket(employee):
    payload = TicketService().issue(employee, "sess-key-1")
    assert "ticket" in payload
    assert payload["expires_in"] == 60


def test_a_ticket_can_only_be_redeemed_once(employee):
    payload = TicketService().issue(employee)
    token = payload["ticket"]

    first = TicketService().redeem(token)
    assert first["emp_id"] == employee.emp_id

    second = TicketService().redeem(token)
    assert second is None


def test_redeeming_an_unknown_token_returns_none():
    assert TicketService().redeem("not-a-real-token") is None


def test_redeeming_an_empty_token_returns_none():
    assert TicketService().redeem("") is None


def test_ticket_falls_back_to_the_database_mirror_when_the_cache_misses(employee):
    """Simulates Daphne and Gunicorn being separate processes with separate
    local-memory caches — the DB mirror is what makes the ticket flow work
    across them."""
    payload = TicketService().issue(employee)
    token = payload["ticket"]

    cache.delete(f"wsticket:{token}")  # the in-process cache "forgets" it

    redeemed = TicketService().redeem(token)
    assert redeemed["emp_id"] == employee.emp_id


def test_purge_expired_tickets_removes_old_rows_only():
    from core.timezone import now_ist

    WebSocketTicket.objects.create(
        token="old", emp_id="E1", expires_at=now_ist() - timedelta(seconds=1)
    )
    WebSocketTicket.objects.create(
        token="fresh", emp_id="E1", expires_at=now_ist() + timedelta(seconds=60)
    )

    deleted = purge_expired_tickets()

    assert deleted == 1
    assert WebSocketTicket.objects.filter(token="fresh").exists()
    assert not WebSocketTicket.objects.filter(token="old").exists()


# ── HTTP: ticket issue + sync catch-up ────────────────────────

def test_ticket_endpoint(as_employee):
    response = as_employee.post("/api/v1/realtime/ticket/")
    assert response.status_code == 200
    assert "ticket" in response.data["data"]
    assert response.data["data"]["ws_url"].endswith("/ws/gateway/")


def test_ticket_endpoint_requires_authentication(api):
    assert api.post("/api/v1/realtime/ticket/").status_code in (401, 403)


def test_sync_replays_events_since_the_given_cursor(as_employee, employee):
    topic = user_group(employee.emp_id)
    old = OutboxEvent.objects.create(topic=topic, audience=topic, event_type="a", payload={})
    new = OutboxEvent.objects.create(topic=topic, audience=topic, event_type="b", payload={})

    import json

    response = as_employee.get(
        "/api/v1/realtime/sync/", {"cursors": json.dumps({topic: old.id})}
    )

    assert response.status_code == 200
    assert response.data["data"]["cursors"][topic] == new.id
    assert response.data["meta"]["count"] == 1


def test_sync_ignores_topics_the_caller_cannot_subscribe_to(as_employee, other_employee):
    import json

    topic = user_group(other_employee.emp_id)
    OutboxEvent.objects.create(topic=topic, audience=topic, event_type="a", payload={})

    response = as_employee.get("/api/v1/realtime/sync/", {"cursors": json.dumps({topic: 0})})
    assert response.data["data"]["events"] == []


def test_sync_rejects_malformed_cursors(as_employee):
    response = as_employee.get("/api/v1/realtime/sync/", {"cursors": "not json"})
    assert response.status_code == 400


def test_sync_requires_authentication(api):
    assert api.get("/api/v1/realtime/sync/").status_code in (401, 403)


# ── the consumer itself, over a real (in-memory) websocket ────

pytestmark_async = pytest.mark.asyncio


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_connects_and_sends_a_ready_frame(employee):
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")

    connected, _ = await communicator.connect()
    assert connected

    frame = await communicator.receive_json_from()
    assert frame["op"] == ServerOp.READY
    assert frame["data"]["emp_id"] == employee.emp_id

    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_rejects_a_missing_ticket():
    communicator = WebsocketCommunicator(application, "/ws/gateway/")
    connected, close_code = await communicator.connect()

    # No ticket and no session cookie -> AnonymousUser -> the consumer closes.
    assert connected is False or close_code == CloseCode.UNAUTHENTICATED
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_ping_pong(employee):
    """connect() also flips presence offline -> online, which broadcasts a
    presence.changed *event* frame to this same socket (it is joined to
    presence.all) — so the reply to our ping can legitimately arrive after
    that unrelated event. Drain until we see the pong, same as a real client
    handling a multiplexed socket would."""
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready frame

    await communicator.send_json_to({"op": "ping"})
    frame = await _receive_until(communicator, lambda f: f["op"] == ServerOp.PONG)

    assert frame["op"] == ServerOp.PONG
    await communicator.disconnect()


async def _receive_until(communicator, predicate, attempts=5):
    """Drain frames until one matches, tolerating an interleaved
    presence.changed broadcast — connect() flips presence offline -> online,
    which this same socket receives as an ordinary event frame alongside
    whatever the test is actually waiting for."""
    for _ in range(attempts):
        frame = await communicator.receive_json_from()
        if predicate(frame):
            return frame
    raise AssertionError(f"no matching frame received within {attempts} frames")


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_refuses_an_unauthorised_subscription(employee, other_employee):
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    await communicator.send_json_to(
        {"op": "sub", "data": {"topic": user_group(other_employee.emp_id)}}
    )
    frame = await _receive_until(communicator, lambda f: f["op"] == ServerOp.ERROR)

    assert frame["data"]["code"] == "forbidden"
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_allows_subscribing_to_your_own_topic(employee):
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    topic = user_group(employee.emp_id)
    await communicator.send_json_to({"op": "sub", "data": {"topic": topic}})
    frame = await _receive_until(communicator, lambda f: f["op"] == "ack")

    assert frame["data"]["subscribed"] is True
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_typing_is_reserved_and_refused(employee):
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    await communicator.send_json_to({"op": "typing", "data": {}})
    frame = await _receive_until(
        communicator, lambda f: f["op"] == ServerOp.ERROR and f["data"]["code"] == "not_implemented"
    )

    assert frame["data"]["code"] == "not_implemented"
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_delivers_a_published_event(employee):
    """The end-to-end path: core.events.publish() -> channel layer ->
    consumer.fanout() -> the client's socket."""
    from channels.db import database_sync_to_async

    from core.events import publish

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    await database_sync_to_async(publish)(
        group=user_group(employee.emp_id), event="work.session.started", data={"id": 1}
    )

    frame = await _receive_until(communicator, lambda f: f.get("type") == "work.session.started")
    assert frame["data"] == {"id": 1}

    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_rejects_a_malformed_frame(employee):
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    await communicator.send_json_to({"nope": "no op field"})
    frame = await _receive_until(communicator, lambda f: f["op"] == ServerOp.ERROR)

    assert frame["op"] == ServerOp.ERROR
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_unsub_removes_the_topic(employee):
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    topic = user_group(employee.emp_id)
    await communicator.send_json_to({"op": "unsub", "data": {"topic": topic}})
    frame = await _receive_until(communicator, lambda f: f["op"] == "ack")

    assert frame["data"]["subscribed"] is False
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_resume_replays_missed_events_for_a_joined_topic(employee):
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    topic = user_group(employee.emp_id)  # already joined at connect via default_groups_for
    event = await database_sync_to_async(OutboxEvent.objects.create)(
        topic=topic, audience=topic, event_type="test.missed", payload={"x": 1}
    )

    await communicator.send_json_to({"op": "resume", "data": {"cursors": {topic: 0}}})
    frame = await _receive_until(communicator, lambda f: f.get("type") == "test.missed")

    assert frame["seq"] == event.id
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_resume_skips_a_topic_the_socket_never_joined(employee, other_employee):
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    unjoined_topic = user_group(other_employee.emp_id)
    await communicator.send_json_to({"op": "resume", "data": {"cursors": {unjoined_topic: 0}}})

    # Nothing to receive — assert the socket is still alive by pinging it.
    await communicator.send_json_to({"op": "ping"})
    frame = await _receive_until(communicator, lambda f: f["op"] == ServerOp.PONG)
    assert frame["op"] == ServerOp.PONG
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_resume_rejects_non_dict_cursors(employee):
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    await communicator.send_json_to({"op": "resume", "data": {"cursors": "not-a-dict"}})
    frame = await _receive_until(communicator, lambda f: f["op"] == ServerOp.ERROR)

    assert frame["data"]["code"] == "bad_frame"
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_presence_set_accepts_a_valid_status(employee):
    """_handle_presence_set sends no reply on success, so send_json_to()
    returning tells us nothing about whether the consumer has actually
    finished processing it — a frame the consumer *does* reply to,
    afterwards, is what proves the earlier one was handled first (Channels
    processes inbound frames on one consumer in order)."""
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    await communicator.send_json_to({"op": "presence.set", "data": {"status": "busy"}})
    await communicator.send_json_to({"op": "ping"})
    await _receive_until(communicator, lambda f: f["op"] == ServerOp.PONG)

    from apps.presence.models import PresenceState

    state = await database_sync_to_async(PresenceState.objects.get)(emp_id=employee.emp_id)
    assert state.status == "busy"
    await communicator.disconnect()
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_presence_set_rejects_an_unsupported_status(employee):
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    await communicator.send_json_to({"op": "presence.set", "data": {"status": "on_break"}})
    frame = await _receive_until(communicator, lambda f: f["op"] == ServerOp.ERROR)

    assert frame["data"]["code"] == "validation_error"
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_subscription_limit_is_enforced(employee, monkeypatch):
    import apps.realtime.consumers as consumers_module

    monkeypatch.setattr(consumers_module, "MAX_TOPICS_PER_SOCKET", 1)
    from channels.db import database_sync_to_async

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    # default_groups_for() already joined several groups at connect, so the
    # patched limit of 1 is already exceeded before any explicit sub.
    await communicator.send_json_to({"op": "sub", "data": {"topic": presence_group()}})
    frame = await _receive_until(communicator, lambda f: f["op"] == ServerOp.ERROR)

    assert frame["data"]["code"] == "too_many_topics"
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_session_revoked_closes_the_matching_socket(employee):
    """connect() queues its own presence.changed broadcast on this socket's
    output (it's joined to presence.all), so the first pending ASGI message
    is not necessarily the close — drain send frames until the close shows
    up, same reasoning as _receive_until for decoded JSON frames."""
    from channels.db import database_sync_to_async

    from core.events import publish

    ticket = await database_sync_to_async(TicketService().issue)(employee, "sess-abc")
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    await database_sync_to_async(publish)(
        group=user_group(employee.emp_id),
        event="session.revoked",
        data={"session_key": "sess-abc"},
        durable=False,
    )

    for _ in range(5):
        output = await communicator.receive_output()
        if output["type"] == "websocket.close":
            break
    else:
        raise AssertionError("socket never closed after session.revoked")

    assert output["type"] == "websocket.close"
    assert output["code"] == CloseCode.UNAUTHENTICATED


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_fanout_excludes_the_actor_who_already_knows(employee):
    """core.events.publish(exclude=...) is how a session-service broadcast
    skips echoing an event back to the person who caused it."""
    from channels.db import database_sync_to_async

    from core.events import publish

    ticket = await database_sync_to_async(TicketService().issue)(employee)
    communicator = WebsocketCommunicator(application, f"/ws/gateway/?ticket={ticket['ticket']}")
    await communicator.connect()
    await communicator.receive_json_from()  # ready

    await database_sync_to_async(publish)(
        group=user_group(employee.emp_id), event="work.session.started",
        data={"id": 1}, exclude=employee.emp_id,
    )

    # Nothing should arrive for this excluded socket — prove liveness with a
    # ping instead of waiting on a frame that will never come.
    await communicator.send_json_to({"op": "ping"})
    frame = await _receive_until(communicator, lambda f: f["op"] == ServerOp.PONG)
    assert frame["op"] == ServerOp.PONG
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_gateway_disconnect_before_connect_does_not_raise():
    """disconnect() guards on hasattr(self, "emp_id") for the case where the
    socket closes before connect() ever set it (e.g. an auth rejection)."""
    communicator = WebsocketCommunicator(application, "/ws/gateway/")
    await communicator.connect()
    await communicator.disconnect()  # must not raise
