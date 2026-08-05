"""Shared validators.

Used by serializers so that a rule lives in one place rather than being
restated at every field that needs it.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.core.exceptions import ValidationError as DjangoValidationError

EMP_ID_RE = re.compile(r"^[A-Za-z0-9_-]{2,20}$")
SAFE_NAME_RE = re.compile(r"^[\w\s().,&/+-]{1,150}$", re.UNICODE)

# Extensions that execute, in some context, on some platform. Blocked
# regardless of what the bytes sniff as.
DANGEROUS_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bat", ".cmd", ".com", ".scr", ".msi",
    ".sh", ".bash", ".zsh", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse",
    ".jar", ".app", ".deb", ".rpm", ".apk", ".php", ".phtml", ".asp", ".aspx",
    ".jsp", ".cgi", ".pl", ".py", ".rb", ".htaccess",
}


def validate_emp_id(value: str) -> str:
    if not value or not EMP_ID_RE.match(value):
        raise DjangoValidationError(
            "Employee ID must be 2-20 characters: letters, digits, hyphen or underscore."
        )
    return value


def validate_non_blank(value: str) -> str:
    """Reject whitespace-only input.

    ``required=True`` alone accepts "   ", which then becomes a master record
    with an invisible name that nobody can find or delete.
    """
    if value is None or not str(value).strip():
        raise DjangoValidationError("This field cannot be blank.")
    return value


def validate_safe_name(value: str) -> str:
    """Master-data names: project, client code, work type."""
    validate_non_blank(value)
    if not SAFE_NAME_RE.match(value.strip()):
        raise DjangoValidationError(
            "Use only letters, numbers, spaces and . , ( ) & / + -"
        )
    return value.strip()


def validate_filename(value: str) -> str:
    """Reject path traversal and executable extensions.

    Files are stored under a UUID name anyway, so this protects the *metadata*
    — an original_name of "../../.bashrc" rendered into a page is still a
    problem even when the bytes are stored safely.
    """
    name = Path(str(value)).name  # strips any directory component
    if not name or name in {".", ".."}:
        raise DjangoValidationError("Invalid filename.")
    if "\x00" in name:
        raise DjangoValidationError("Invalid filename.")
    if Path(name).suffix.lower() in DANGEROUS_EXTENSIONS:
        raise DjangoValidationError("That file type is not permitted.")
    return name


def validate_positive(value) -> int | float:
    if value is None or value < 0:
        raise DjangoValidationError("Must be zero or greater.")
    return value


def validate_work_units(value: int) -> int:
    """Sanity bound on manual entry.

    Someone typing 100000 instead of 1000 skews a productivity average for the
    whole month, and nobody notices until the client asks.
    """
    validate_positive(value)
    if value > 100_000:
        raise DjangoValidationError("That is more work units than a shift can contain.")
    return value


def validate_date_range(start, end) -> None:
    if start and end and start > end:
        raise DjangoValidationError("The start date must be on or before the end date.")
