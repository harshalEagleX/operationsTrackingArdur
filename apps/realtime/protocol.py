"""The wire protocol.

Every frame in both directions is the same envelope::

    {
      "v": 1,
      "op": "event",
      "topic": "user.E1042",
      "type": "break.started",
      "seq": 918233,
      "ts": "2026-08-05T14:22:11+05:30",
      "data": {}
    }

Client→server ops are deliberately few. **Writes go over HTTP; pushes come
over the WebSocket.** The exceptions are ``ping`` and ``typing``, which are
ephemeral and never persisted.

Why not send writes over the socket: one validation path, one permission path,
one throttle, one audit trail. HTTP gives you a status code — a dropped frame
gives you silence. The extra 30 ms is invisible behind optimistic UI.
"""

from __future__ import annotations

from typing import Any

from core.timezone import now_ist

VERSION = 1


class ClientOp:
    """Ops the browser may send."""

    PING = "ping"
    SUB = "sub"
    UNSUB = "unsub"
    RESUME = "resume"
    TYPING = "typing"  # reserved for chat
    PRESENCE_SET = "presence.set"

    ALL = frozenset({PING, SUB, UNSUB, RESUME, TYPING, PRESENCE_SET})


class ServerOp:
    """Ops the server may send."""

    READY = "ready"
    PONG = "pong"
    EVENT = "event"
    ERROR = "error"
    ACK = "ack"


class CloseCode:
    """WebSocket close codes in the private 4000-4999 range.

    4401 is the one that matters to the client: it means "your session is
    gone, go to /login" rather than "the connection dropped, reconnect".
    Treating them the same produces an infinite reconnect loop against an
    endpoint that will never accept you.
    """

    UNAUTHENTICATED = 4401
    FORBIDDEN = 4403
    RATE_LIMITED = 4429
    SERVER_ERROR = 4500
    GOING_AWAY = 4000


def envelope(op: str, *, topic: str | None = None, event_type: str | None = None,
             data: Any = None, seq: int | None = None) -> dict:
    frame = {"v": VERSION, "op": op, "ts": now_ist().isoformat()}
    if topic is not None:
        frame["topic"] = topic
    if event_type is not None:
        frame["type"] = event_type
    if seq is not None:
        frame["seq"] = seq
    if data is not None:
        frame["data"] = data
    return frame


def error_frame(code: str, message: str) -> dict:
    return envelope(ServerOp.ERROR, data={"code": code, "message": message})


def pong_frame() -> dict:
    return envelope(ServerOp.PONG)


def ready_frame(*, emp_id: str, cursors: dict, heartbeat_interval: int,
                groups: list[str]) -> dict:
    return envelope(
        ServerOp.READY,
        data={
            "emp_id": emp_id,
            "server_time": now_ist().isoformat(),
            "heartbeat_interval": heartbeat_interval,
            "cursors": cursors,
            "topics": groups,
            "protocol_version": VERSION,
        },
    )


def is_valid_client_frame(frame: Any) -> tuple[bool, str]:
    """Validate an inbound frame. Returns (ok, reason)."""
    if not isinstance(frame, dict):
        return False, "Frame must be a JSON object."

    op = frame.get("op")
    if not op:
        return False, "Frame is missing 'op'."
    if op not in ClientOp.ALL:
        return False, f"Unknown op '{op}'."

    if frame.get("v", VERSION) != VERSION:
        return False, f"Unsupported protocol version {frame.get('v')}."

    return True, ""
