"""File background tasks."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task

from apps.files.models import StoredFile
from apps.files.storage import storage_root
from core.timezone import now_ist

logger = logging.getLogger("opstracking.tasks")

THUMBNAIL_MAX = (480, 480)
ORPHAN_AGE_HOURS = 24


@shared_task(bind=True, max_retries=2)
def make_thumbnail(self, stored_file_id: int):
    """Generate a thumbnail and strip EXIF.

    Stripping EXIF is not cosmetic: phone photos carry GPS coordinates, and an
    employee sharing a screenshot should not be sharing their home address.
    """
    from PIL import Image, ImageOps

    stored = StoredFile.objects.filter(pk=stored_file_id).first()
    if not stored or not stored.is_image:
        return {"ok": False, "reason": "not an image"}

    try:
        source = stored.absolute_path
        relative_thumb = f"thumbs/{stored.uuid}.webp"
        destination = storage_root() / relative_thumb
        destination.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(source) as image:
            # Honour the EXIF orientation tag before discarding EXIF, or
            # portrait photos come out sideways.
            image = ImageOps.exif_transpose(image)
            image.thumbnail(THUMBNAIL_MAX)

            # Re-encoding through a fresh image drops every metadata block.
            clean = Image.new(image.mode, image.size)
            clean.putdata(list(image.getdata()))
            clean.save(destination, "WEBP", quality=82)

        destination.chmod(0o640)
        StoredFile.objects.filter(pk=stored.pk).update(thumb_path=relative_thumb)

    except Exception as exc:
        logger.exception("thumbnail failed for file %s", stored_file_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30) from exc
        # A missing thumbnail is a cosmetic failure. The original is intact
        # and downloadable, so do not fail loudly forever.
        return {"ok": False, "error": str(exc)[:200]}

    return {"ok": True, "thumb": relative_thumb}


@shared_task
def collect_orphaned_uploads(older_than_hours: int = ORPHAN_AGE_HOURS):
    """Delete uploads that were never attached to anything.

    The two-step upload means closing a tab mid-compose leaves bytes on disk
    with no owner record. Without this, storage grows forever.
    """
    from apps.files.services import FileService

    cutoff = now_ist() - timedelta(hours=older_than_hours)
    orphans = StoredFile.objects.orphaned(cutoff)

    removed = 0
    for stored in orphans.iterator():
        try:
            FileService._unlink(stored)
            stored.delete()
            removed += 1
        except Exception:
            logger.exception("could not remove orphaned upload %s", stored.pk)

    if removed:
        logger.info("collected %d orphaned uploads older than %dh", removed, older_than_hours)
    return {"removed": removed}


@shared_task
def scan_file(stored_file_id: int):
    """Hook for a virus scanner (ClamAV or similar).

    Not wired up: there is no scanner on the box yet, and a stub that always
    returns 'clean' while looking like a scan is worse than no scan at all.
    Files are marked clean at upload after the magic-byte and extension gate.

    To enable: install clamd, call it here, and set scan_status from the
    result — then flip FileService.store() to create files as PENDING.
    """
    logger.debug("scan_file called for %s — no scanner configured", stored_file_id)
    return {"ok": True, "scanned": False, "reason": "no scanner configured"}
