"""Private file storage.

Everything uploaded lands under ``PRIVATE_STORAGE_ROOT``, which is outside the
web root. There is no URL that reaches these bytes directly — every read goes
through apps.files.views.FileDownloadView, which checks permissions first.

The alternative (files under /static/ with unguessable names) is security by
URL secrecy, and URLs leak: into referrer headers, into chat logs, into the
browser history of a shared machine.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    """Filesystem storage rooted outside the document root.

    ``base_url`` is None deliberately: calling ``.url()`` on a stored file
    raises instead of silently producing a path Apache would refuse to serve
    anyway. Use ``StoredFile.download_url`` instead.
    """

    def __init__(self, location=None, base_url=None, **kwargs):
        location = location or str(settings.PRIVATE_STORAGE_ROOT)
        super().__init__(
            location=location,
            base_url=None,
            file_permissions_mode=getattr(settings, "FILE_UPLOAD_PERMISSIONS", 0o640),
            directory_permissions_mode=0o750,
            **kwargs,
        )

    def url(self, name):  # pragma: no cover
        raise NotImplementedError(
            "Private files have no public URL. Use StoredFile.download_url, which "
            "routes through the permission-checked download view."
        )


def storage_root() -> Path:
    return Path(settings.PRIVATE_STORAGE_ROOT)


def ensure_directories() -> None:
    """Create the storage tree with restrictive permissions.

    Called by ``manage.py bootstrap_storage`` and by the dev seed command so a
    fresh clone can accept an upload immediately.
    """
    root = storage_root()
    for sub in (
        "uploads/feedback",
        "uploads/allocations",
        "uploads/chat",
        "uploads/misc",
        "thumbs",
        "exports",
    ):
        path = root / sub
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o750)


def safe_join(relative_path: str) -> Path:
    """Resolve a stored path against the root, refusing to escape it.

    ``stored_path`` comes from our own database, but a bug or a bad migration
    could still put ``../../etc/passwd`` there, and this is the last line
    before an open().
    """
    root = storage_root().resolve()
    candidate = (root / relative_path).resolve()

    if not candidate.is_relative_to(root):
        raise ValueError(f"Refusing to read outside the storage root: {relative_path!r}")

    return candidate
