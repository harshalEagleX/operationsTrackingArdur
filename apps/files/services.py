"""File storage service.

Non-negotiables enforced here:

  * The stored filename is a UUID. The user's filename is metadata only, so
    path traversal has nowhere to go.
  * Files land outside the web root, mode 0640 — Apache's user cannot read
    them; only the app user can.
  * SHA-256 is recorded, giving free deduplication and a tamper check.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.files.models import FileContext, ScanStatus, StoredFile
from apps.files.scanners import is_image, validate
from apps.files.storage import ensure_directories, storage_root
from core.exceptions import NotFoundError, PermissionDeniedError
from core.services import BaseService
from core.timezone import now_ist
from core.validators import validate_filename

logger = logging.getLogger("opstracking.files")


class FileService(BaseService):
    """Store, claim and delete files."""

    @transaction.atomic
    def store(self, uploaded, context: str = FileContext.MISC) -> StoredFile:
        actor = self.require_actor()

        mime_type = validate(uploaded)
        original_name = validate_filename(uploaded.name)

        digest = hashlib.sha256()
        for chunk in uploaded.chunks():
            digest.update(chunk)
        uploaded.seek(0)
        sha256 = digest.hexdigest()

        record = StoredFile(
            owner_emp_id=actor.emp_id,
            context=context,
            original_name=original_name[:255],
            mime_type=mime_type,
            size_bytes=uploaded.size,
            sha256=sha256,
            scan_status=ScanStatus.CLEAN,
            created_at=now_ist(),
        )

        extension = Path(original_name).suffix.lower()
        relative = f"uploads/{context}/{now_ist():%Y/%m}/{record.uuid}{extension}"
        absolute = storage_root() / relative

        ensure_directories()
        absolute.parent.mkdir(parents=True, exist_ok=True)

        with open(absolute, "wb") as handle:
            for chunk in uploaded.chunks():
                handle.write(chunk)
        absolute.chmod(getattr(settings, "FILE_UPLOAD_PERMISSIONS", 0o640))

        record.stored_path = relative
        record.save()

        self.log("file_stored", id=record.id, size=record.size_bytes, mime=mime_type)

        if is_image(mime_type):
            from apps.files.tasks import make_thumbnail

            self.on_commit(lambda: make_thumbnail.delay(record.id))

        return record

    @transaction.atomic
    def claim(self, file_ids: list[int], context: str) -> list[StoredFile]:
        """Attach previously uploaded files to a record.

        Ownership is re-checked here, not only at upload: without it, a user
        could reference someone else's file id in their own feedback and pull
        the bytes into a record they are allowed to read.
        """
        actor = self.require_actor()

        files = list(StoredFile.objects.filter(id__in=file_ids))

        found_ids = {f.id for f in files}
        missing = set(file_ids) - found_ids
        if missing:
            raise NotFoundError(f"Upload {sorted(missing)[0]} was not found.")

        for stored in files:
            if stored.owner_emp_id != actor.emp_id and not actor.is_admin:
                raise PermissionDeniedError("That upload belongs to someone else.")
            if stored.scan_status != ScanStatus.CLEAN:
                raise PermissionDeniedError(f"{stored.original_name} has not been cleared.")

        StoredFile.objects.filter(id__in=found_ids).update(
            claimed_at=now_ist(), context=context
        )
        return files

    @transaction.atomic
    def delete(self, stored: StoredFile) -> None:
        actor = self.require_actor()
        if stored.owner_emp_id != actor.emp_id and not actor.is_admin:
            raise PermissionDeniedError("That file belongs to someone else.")

        self._unlink(stored)
        file_id = stored.id
        stored.delete()
        self.log("file_deleted", id=file_id)

    @staticmethod
    def _unlink(stored: StoredFile) -> None:
        """Remove the bytes. Missing files are not an error — the row is what
        we are actually deleting."""
        for path in (stored.stored_path, stored.thumb_path):
            if not path:
                continue
            try:
                (storage_root() / path).unlink(missing_ok=True)
            except OSError:
                logger.exception("could not unlink %s", path)


class FileAccessPolicy:
    """Who may download which file.

    Called on every download. The rule for a feedback image is the same as the
    rule for the feedback record it belongs to — applied to bytes instead of
    rows, so an attachment cannot be the way around a permission check.
    """

    def __init__(self, user):
        self.user = user

    def can_read(self, stored: StoredFile) -> bool:
        if self.user is None or not self.user.is_authenticated:
            return False

        if self.user.is_admin:
            return True

        if stored.owner_emp_id == self.user.emp_id:
            return True

        checker = {
            FileContext.FEEDBACK: self._can_read_feedback_file,
            FileContext.EXPORT: self._can_read_export,
            FileContext.ALLOCATION: self._can_read_allocation_file,
            FileContext.CHAT: self._can_read_chat_file,
        }.get(stored.context)

        return checker(stored) if checker else False

    def _can_read_feedback_file(self, stored: StoredFile) -> bool:
        from apps.feedback.models import Feedback

        return Feedback.objects.visible_to(self.user).filter(
            images__file_id=stored.id
        ).exists()

    def _can_read_export(self, stored: StoredFile) -> bool:
        from apps.reports.models import ReportJob

        return ReportJob.objects.filter(
            file_id=stored.id, requested_by=self.user.emp_id
        ).exists()

    def _can_read_allocation_file(self, stored: StoredFile) -> bool:
        return self.user.is_supervisor

    def _can_read_chat_file(self, stored: StoredFile) -> bool:
        """Chat is not implemented yet.

        Returning False rather than True is the safe default: when
        apps.chat lands, this becomes "is the user a participant in the
        conversation this attachment's message belongs to?".
        """
        return False
