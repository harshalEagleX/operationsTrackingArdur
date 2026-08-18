"""Break allowances — owned by the server, never sent by the client.

The previous implementation accepted ``allotted_time`` in the request body,
which meant anyone could give themselves a four-hour tea break by editing one
number in devtools. These constants are the only source of that value; the
serializer has no field for it.

Changing an allowance is a deploy, deliberately. If it needs to be editable at
runtime, move it into ot_shift_master and read it through BreakService — do
not add it to the request.
"""

from __future__ import annotations

# Break type → allowance in seconds.
BREAK_ALLOWANCES: dict[str, int] = {
    "Tea break 1": 5 * 60,
    "Meal break": 35 * 60,
    "Tea break 2": 5 * 60,
}

# Break types an employee may take more than once a day. Everything else is
# once per shift.
REPEATABLE_BREAKS: frozenset[str] = frozenset({"Rest room", "Technical issue"})

# How far past the allowance before the overrun alert fires. A little grace
# stops the system nagging someone who is thirty seconds late back.
OVERRUN_GRACE_SECONDS = 120


def allowance_for(break_type: str) -> int | None:
    """Seconds allowed for this break type, or None if it is not a real type."""
    return BREAK_ALLOWANCES.get(break_type)


def is_repeatable(break_type: str) -> bool:
    return break_type in REPEATABLE_BREAKS


def break_type_choices() -> list[tuple[str, str]]:
    return [(key, key) for key in BREAK_ALLOWANCES]
