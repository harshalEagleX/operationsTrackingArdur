"""The notification type catalogue.

A registry rather than strings scattered across the codebase. Adding a type
means adding one entry here, which is also the list the preferences screen
renders from — so a new notification is automatically something a user can
turn off.
"""

from __future__ import annotations

from dataclasses import dataclass


class Priority:
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class NotificationType:
    key: str
    title_template: str
    description: str = ""
    default_in_app: bool = True
    default_email: bool = False
    priority: str = Priority.NORMAL
    # False for types a user must not be able to silence.
    user_configurable: bool = True


REGISTRY: dict[str, NotificationType] = {
    t.key: t
    for t in [
        NotificationType(
            "allocation.assigned",
            "New order {task_id} assigned to you",
            description="Work has been allocated to you",
            priority=Priority.HIGH,
        ),
        NotificationType(
            "allocation.sla_breach",
            "SLA breach risk on {task_id}",
            description="An allocation is close to its due time",
            priority=Priority.CRITICAL,
            default_email=True,
            user_configurable=False,
        ),
        NotificationType(
            "feedback.received",
            "Quality feedback on {order_batch_id}",
            description="A supervisor recorded feedback about your work",
            priority=Priority.HIGH,
            user_configurable=False,
        ),
        NotificationType(
            "break.overrun",
            "Your {break_type} has exceeded {allotted} minutes",
            description="A break has run past its allowance",
            priority=Priority.NORMAL,
        ),
        NotificationType(
            "work.target_met",
            "Daily target met for {project}",
            description="You hit your target for the day",
            priority=Priority.LOW,
        ),
        NotificationType(
            "report.ready",
            "Your {report_key} export is ready",
            description="A report you requested has finished generating",
            priority=Priority.NORMAL,
        ),
        NotificationType(
            "report.failed",
            "Your {report_key} export could not be generated",
            description="A report you requested failed",
            priority=Priority.NORMAL,
            user_configurable=False,
        ),
        # ── reserved for apps.chat ────────────────────────────
        NotificationType(
            "chat.mention",
            "{actor_name} mentioned you",
            description="Someone mentioned you in a conversation",
            priority=Priority.HIGH,
        ),
        NotificationType(
            "chat.message",
            "New message from {actor_name}",
            description="A message arrived while you were away",
            priority=Priority.LOW,
        ),
    ]
}


def get(key: str) -> NotificationType:
    try:
        return REGISTRY[key]
    except KeyError:
        raise KeyError(
            f"Unknown notification type {key!r}. Add it to apps/notifications/registry.py "
            f"— known types: {', '.join(sorted(REGISTRY))}"
        ) from None


def configurable_types() -> list[NotificationType]:
    """What the preferences screen offers."""
    return [t for t in REGISTRY.values() if t.user_configurable]


def render_title(key: str, context: dict) -> str:
    """Fill a title template, tolerating a missing key.

    A KeyError here would turn a missing context value into a 500 on an
    otherwise successful business action — the notification is the least
    important thing happening in that request.
    """
    spec = get(key)
    try:
        return spec.title_template.format(**context)
    except (KeyError, IndexError):
        return spec.title_template
