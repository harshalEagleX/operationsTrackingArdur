"""Channel group names.

Built here rather than inlined as f-strings, so a rename is one edit and a
typo is a failed import instead of a socket that silently receives nothing.

Every socket joins ``user.{emp_id}`` and ``presence.all`` at connect.
"""

from __future__ import annotations

import re

USER = "user.{emp_id}"
PRESENCE_ALL = "presence.all"
PROJECT = "project.{project_id}"
ROLE = "role.{role}"
CONVERSATION = "chat.conv.{conversation_id}"  # reserved for apps.chat

# Channels requires group names to be ASCII alphanumerics, hyphens, underscores
# or periods, and under 100 characters.
GROUP_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,99}$")


def _sanitise(value) -> str:
    """Make an arbitrary identifier safe as a group-name component."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", str(value))[:60]


def user_group(emp_id: str) -> str:
    return USER.format(emp_id=_sanitise(emp_id))


def presence_group() -> str:
    return PRESENCE_ALL


def project_group(project_id) -> str:
    return PROJECT.format(project_id=_sanitise(project_id))


def role_group(role: str) -> str:
    return ROLE.format(role=_sanitise(role))


def conversation_group(conversation_id) -> str:
    """Reserved for chat. Kept here so the naming scheme stays in one file."""
    return CONVERSATION.format(conversation_id=_sanitise(conversation_id))


def is_valid_group(name: str) -> bool:
    return bool(name) and bool(GROUP_NAME_RE.match(name))


def default_groups_for(user) -> list[str]:
    """The groups every socket joins at connect."""
    groups = [user_group(user.emp_id), presence_group(), role_group(user.role)]

    employee = user.employee
    if employee and employee.project:
        groups.append(project_group(employee.project))

    return groups


def can_subscribe(user, topic: str) -> bool:
    """Authorise a client-requested subscription.

    This is not optional. Without it any authenticated user can send
    ``{"op":"sub","data":{"topic":"user.E1042"}}`` and read another employee's
    event stream — the websocket equivalent of reading their records.
    """
    if user is None or not user.is_authenticated or not is_valid_group(topic):
        return False

    # Your own user topic, always.
    if topic == user_group(user.emp_id):
        return True

    # The shared presence roster.
    if topic == presence_group():
        return True

    # Your own role topic.
    if topic == role_group(user.role):
        return True

    # A project topic you are actually assigned to; supervisors see all.
    if topic.startswith("project."):
        if user.is_supervisor:
            return True
        employee = user.employee
        return bool(employee and topic == project_group(employee.project))

    # Another user's topic — supervisors included. Nobody rides someone
    # else's socket stream.
    if topic.startswith("user."):
        return False

    # Chat conversations are not implemented; refuse until apps.chat lands
    # and can answer "is this user a participant?".
    if topic.startswith("chat."):
        return False

    return False
