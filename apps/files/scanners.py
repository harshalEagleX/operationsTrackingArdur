"""Upload validation gate.

Order matters, and each check exists because the one before it can be beaten:

  1. Size, before reading anything — a 4 GB upload must not be buffered first.
  2. Magic bytes. ``uploaded.content_type`` is supplied by the browser, which
     is supplied by the attacker. Only the actual bytes are evidence.
  3. Extension must agree with the sniffed type. This is where ``payload.exe``
     renamed to ``photo.jpg`` dies.
  4. Explicit blocklist of executable extensions, regardless of content.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings

from core.exceptions import ValidationError
from core.validators import DANGEROUS_EXTENSIONS

logger = logging.getLogger("opstracking.files")

# Sniffed MIME type → the extensions that legitimately carry it.
ALLOWED_TYPES: dict[str, list[str]] = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/webp": [".webp"],
    "image/gif": [".gif"],
    "application/pdf": [".pdf"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    "application/vnd.ms-excel": [".xls"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    "application/msword": [".doc"],
    "text/csv": [".csv"],
    "text/plain": [".txt", ".csv"],
    "application/zip": [".xlsx", ".docx"],  # OOXML files sniff as zip on some libmagic builds
}

IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})


def _sniff(head: bytes) -> str:
    """Read the real MIME type from the leading bytes."""
    try:
        import magic
    except ImportError:  # pragma: no cover
        logger.error(
            "python-magic/libmagic is not installed — uploads cannot be validated. "
            "Install libmagic (brew install libmagic / dnf install file-devel)."
        )
        raise ValidationError(
            "File uploads are unavailable right now. Please contact support.",
            code="upload_unavailable",
        ) from None

    return magic.from_buffer(head, mime=True)


def validate(uploaded) -> str:
    """Validate an uploaded file and return its sniffed MIME type.

    Raises ValidationError with a specific code the frontend can act on.
    """
    max_bytes = getattr(settings, "MAX_UPLOAD_BYTES", 25 * 1024 * 1024)

    if uploaded.size == 0:
        raise ValidationError("That file is empty.", code="file_empty")

    if uploaded.size > max_bytes:
        raise ValidationError(
            f"That file is {uploaded.size // (1024 * 1024)} MB. "
            f"The limit is {max_bytes // (1024 * 1024)} MB.",
            code="file_too_large",
        )

    name = Path(uploaded.name or "").name
    extension = Path(name).suffix.lower()

    if not extension:
        raise ValidationError("That file has no extension.", code="file_type_blocked")

    if extension in DANGEROUS_EXTENSIONS:
        raise ValidationError(
            f"{extension} files are not permitted.", code="file_type_blocked"
        )

    head = uploaded.read(2048)
    uploaded.seek(0)

    sniffed = _sniff(head)

    if sniffed not in ALLOWED_TYPES:
        logger.warning("blocked upload %r: sniffed as %s", name, sniffed)
        raise ValidationError(
            "That file type is not permitted. Allowed: images, PDF, Word, Excel, CSV and text.",
            code="file_type_blocked",
        )

    if extension not in ALLOWED_TYPES[sniffed]:
        logger.warning(
            "blocked upload %r: extension %s does not match sniffed type %s",
            name, extension, sniffed,
        )
        raise ValidationError(
            "The file's contents do not match its extension.",
            code="file_type_blocked",
        )

    return sniffed


def is_image(mime_type: str) -> bool:
    return mime_type in IMAGE_TYPES
