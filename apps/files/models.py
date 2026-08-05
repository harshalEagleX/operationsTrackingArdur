"""Stored file metadata.

The bytes live on disk under a UUID name; this table is everything we know
about them. One table for every context (feedback images, allocation imports,
report exports, and later chat attachments) so there is one upload path to
secure rather than four.
"""

from __future__ import annotations

import uuid as uuid_lib

from django.db import models
from django.urls import reverse

from core.timezone import now_ist


class FileContext(models.TextChoices):
    FEEDBACK = "feedback", "Feedback image"
    ALLOCATION = "allocation", "Allocation import"
    EXPORT = "export", "Report export"
    CHAT = "chat", "Chat attachment"
    MISC = "misc", "Other"


class ScanStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CLEAN = "clean", "Clean"
    BLOCKED = "blocked", "Blocked"


class StoredFileQuerySet(models.QuerySet):
    def clean(self):
        return self.filter(scan_status=ScanStatus.CLEAN)

    def orphaned(self, older_than):
        """Uploaded but never attached to anything.

        The two-step upload means a user can upload a file and then close the
        tab. Those rows are collected nightly.
        """
        return self.filter(claimed_at__isnull=True, created_at__lt=older_than)


class StoredFile(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)

    owner_emp_id = models.CharField(max_length=20, db_index=True)
    context = models.CharField(
        max_length=20, choices=FileContext.choices, default=FileContext.MISC
    )

    original_name = models.CharField(max_length=255)
    stored_path = models.CharField(max_length=500, help_text="Relative to PRIVATE_STORAGE_ROOT")
    thumb_path = models.CharField(max_length=500, blank=True, default="")

    # Sniffed from the bytes, never taken from the request.
    mime_type = models.CharField(max_length=120)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)

    scan_status = models.CharField(
        max_length=10, choices=ScanStatus.choices, default=ScanStatus.PENDING
    )
    # Null until something references it; used to collect abandoned uploads.
    claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=now_ist, db_index=True)

    objects = StoredFileQuerySet.as_manager()

    class Meta:
        db_table = "ot_stored_files"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner_emp_id", "context"], name="ix_file_owner_ctx"),
        ]

    def __str__(self) -> str:
        return f"{self.original_name} ({self.size_bytes} bytes)"

    @property
    def absolute_path(self):
        from apps.files.storage import safe_join

        return safe_join(self.stored_path)

    @property
    def absolute_thumb_path(self):
        from apps.files.storage import safe_join

        return safe_join(self.thumb_path) if self.thumb_path else None

    @property
    def download_url(self) -> str:
        return reverse("api:files:download", kwargs={"file_uuid": str(self.uuid)})

    @property
    def thumbnail_url(self) -> str | None:
        if not self.thumb_path:
            return None
        return reverse("api:files:thumbnail", kwargs={"file_uuid": str(self.uuid)})

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")

    @property
    def size_display(self) -> str:
        size = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"
