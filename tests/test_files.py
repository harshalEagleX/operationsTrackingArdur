"""File upload, storage and download.

Uploads are validated by content, not filename — magic-byte sniffing needs
real bytes (a Pillow-generated PNG, an actual PDF header), not filenames with
the right extension and garbage inside.
"""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.files.models import FileContext, ScanStatus, StoredFile
from apps.files.scanners import is_image, validate
from apps.files.services import FileAccessPolicy, FileService
from apps.files.storage import safe_join, storage_root
from core.exceptions import NotFoundError, PermissionDeniedError, ValidationError

pytestmark = pytest.mark.django_db


def _png_bytes() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"0" * 200


def _png_upload(name="photo.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, _png_bytes(), content_type="image/png")


# ── scanners.validate(): the upload gate ─────────────────────

def test_validate_accepts_a_real_png():
    mime = validate(_png_upload())
    assert mime == "image/png"


def test_validate_accepts_a_real_pdf():
    upload = SimpleUploadedFile("doc.pdf", _pdf_bytes(), content_type="application/pdf")
    assert validate(upload) == "application/pdf"


def test_validate_rejects_an_empty_file():
    upload = SimpleUploadedFile("empty.png", b"", content_type="image/png")
    with pytest.raises(ValidationError) as exc:
        validate(upload)
    assert exc.value.code == "file_empty"


def test_validate_rejects_a_file_over_the_size_limit(settings):
    settings.MAX_UPLOAD_BYTES = 100
    upload = SimpleUploadedFile("big.png", _png_bytes() + b"0" * 500, content_type="image/png")
    with pytest.raises(ValidationError) as exc:
        validate(upload)
    assert exc.value.code == "file_too_large"


def test_validate_rejects_a_file_with_no_extension():
    upload = SimpleUploadedFile("noext", _png_bytes(), content_type="image/png")
    with pytest.raises(ValidationError) as exc:
        validate(upload)
    assert exc.value.code == "file_type_blocked"


def test_validate_rejects_a_dangerous_extension_regardless_of_content():
    """An .exe with real PNG bytes inside — the extension blocklist runs
    before sniffing even matters."""
    upload = SimpleUploadedFile("payload.exe", _png_bytes(), content_type="image/png")
    with pytest.raises(ValidationError) as exc:
        validate(upload)
    assert exc.value.code == "file_type_blocked"


def test_validate_rejects_content_that_does_not_match_its_extension():
    """This is the payload.exe-renamed-to-photo.jpg case: real PNG bytes
    wearing a .pdf extension."""
    upload = SimpleUploadedFile("photo.pdf", _png_bytes(), content_type="application/pdf")
    with pytest.raises(ValidationError) as exc:
        validate(upload)
    assert exc.value.code == "file_type_blocked"


def test_validate_rejects_an_unrecognised_type():
    upload = SimpleUploadedFile("data.bin", b"\x00\x01\x02\x03" * 50, content_type="application/octet-stream")
    with pytest.raises(ValidationError) as exc:
        validate(upload)
    assert exc.value.code == "file_type_blocked"


def test_validate_ignores_the_browser_supplied_content_type():
    """content_type is attacker-controlled; only the sniffed bytes matter."""
    upload = SimpleUploadedFile("photo.png", _png_bytes(), content_type="text/plain")
    assert validate(upload) == "image/png"


def test_validate_leaves_the_stream_position_reset_for_later_reads():
    upload = _png_upload()
    validate(upload)
    assert upload.tell() == 0


def test_is_image_true_for_image_mimes_only():
    assert is_image("image/png") is True
    assert is_image("application/pdf") is False


# ── storage.safe_join(): path traversal ──────────────────────

def test_safe_join_resolves_a_normal_relative_path():
    path = safe_join("uploads/misc/2026/01/somefile.png")
    assert path.is_relative_to(storage_root().resolve())


def test_safe_join_refuses_to_escape_the_storage_root():
    with pytest.raises(ValueError):
        safe_join("../../../../etc/passwd")


def test_safe_join_refuses_an_absolute_path_outside_root():
    with pytest.raises(ValueError):
        safe_join("/etc/passwd")


# ── FileService.store / claim / delete ───────────────────────

def test_store_creates_a_row_and_writes_bytes_to_disk(employee):
    stored = FileService(actor=employee).store(_png_upload(), context=FileContext.MISC)

    assert stored.owner_emp_id == employee.emp_id
    assert stored.mime_type == "image/png"
    assert stored.scan_status == ScanStatus.CLEAN
    assert stored.absolute_path.exists()
    assert stored.sha256  # content hash recorded


def test_store_uses_a_uuid_filename_not_the_original(employee):
    stored = FileService(actor=employee).store(
        SimpleUploadedFile("../../etc/passwd.png", _png_bytes(), content_type="image/png"),
        context=FileContext.MISC,
    )
    assert str(stored.uuid) in stored.stored_path
    assert "passwd" not in stored.stored_path


def test_store_sets_restrictive_permissions(employee):
    stored = FileService(actor=employee).store(_png_upload(), context=FileContext.MISC)
    mode = stored.absolute_path.stat().st_mode & 0o777
    assert mode == 0o640


def test_store_requires_an_actor():
    with pytest.raises(PermissionDeniedError):
        FileService(actor=None).store(_png_upload())


def test_store_rejects_an_export_context_from_a_manual_upload(employee):
    """Serializer-level rule, but the same guard is worth pinning at the
    service boundary too — exports are produced by the server, not uploaded."""
    from apps.files.serializers import FileUploadSerializer

    serializer = FileUploadSerializer(data={"file": _png_upload(), "context": "export"})
    assert not serializer.is_valid()
    assert "context" in serializer.errors


def test_claim_attaches_files_the_caller_owns(employee):
    stored = FileService(actor=employee).store(_png_upload())
    claimed = FileService(actor=employee).claim([stored.id], context=FileContext.FEEDBACK)

    assert len(claimed) == 1
    stored.refresh_from_db()
    assert stored.claimed_at is not None
    assert stored.context == FileContext.FEEDBACK


def test_claim_refuses_someone_elses_upload(employee, other_employee):
    stored = FileService(actor=other_employee).store(_png_upload())

    with pytest.raises(PermissionDeniedError):
        FileService(actor=employee).claim([stored.id], context=FileContext.FEEDBACK)


def test_claim_admin_may_claim_anyones_upload(employee, admin):
    stored = FileService(actor=employee).store(_png_upload())
    claimed = FileService(actor=admin).claim([stored.id], context=FileContext.FEEDBACK)
    assert len(claimed) == 1


def test_claim_raises_not_found_for_a_missing_id(employee):
    with pytest.raises(NotFoundError):
        FileService(actor=employee).claim([999999], context=FileContext.FEEDBACK)


def test_delete_removes_the_row_and_the_bytes(employee):
    stored = FileService(actor=employee).store(_png_upload())
    path = stored.absolute_path
    assert path.exists()

    FileService(actor=employee).delete(stored)

    assert not path.exists()
    assert not StoredFile.objects.filter(pk=stored.pk).exists()


def test_delete_refuses_someone_elses_file(employee, other_employee):
    stored = FileService(actor=other_employee).store(_png_upload())
    with pytest.raises(PermissionDeniedError):
        FileService(actor=employee).delete(stored)


def test_delete_tolerates_bytes_already_missing_from_disk(employee):
    """The row is what we are actually deleting; a missing file must not
    raise."""
    stored = FileService(actor=employee).store(_png_upload())
    stored.absolute_path.unlink()

    FileService(actor=employee).delete(stored)  # must not raise
    assert not StoredFile.objects.filter(pk=stored.pk).exists()


# ── size_display / is_image / URLs ───────────────────────────

def test_size_display_formats_bytes_and_kb():
    assert StoredFile(size_bytes=500).size_display == "500 B"
    assert StoredFile(size_bytes=2048).size_display == "2.0 KB"


def test_download_url_is_permission_checked_not_direct(employee):
    stored = FileService(actor=employee).store(_png_upload())
    assert str(stored.uuid) in stored.download_url
    assert stored.download_url.startswith("/api/v1/files/")


# ── FileAccessPolicy ──────────────────────────────────────────

def test_owner_can_always_read_their_own_file(employee):
    stored = FileService(actor=employee).store(_png_upload())
    assert FileAccessPolicy(employee).can_read(stored) is True


def test_admin_can_read_anyones_file(employee, admin):
    stored = FileService(actor=employee).store(_png_upload())
    assert FileAccessPolicy(admin).can_read(stored) is True


def test_anonymous_cannot_read_any_file(employee):
    from django.contrib.auth.models import AnonymousUser

    stored = FileService(actor=employee).store(_png_upload())
    assert FileAccessPolicy(AnonymousUser()).can_read(stored) is False


def test_a_strangers_misc_file_is_not_readable(employee, other_employee):
    stored = FileService(actor=other_employee).store(_png_upload(), context=FileContext.MISC)
    assert FileAccessPolicy(employee).can_read(stored) is False


def test_feedback_image_readable_by_whoever_can_read_the_feedback(employee, supervisor):
    from apps.feedback.models import Feedback, FeedbackImage

    stored = FileService(actor=supervisor).store(_png_upload(), context=FileContext.FEEDBACK)
    feedback = Feedback.objects.create(
        emp_id=employee.emp_id, subject="Coaching note", created_by=supervisor.emp_id
    )
    FeedbackImage.objects.create(feedback=feedback, file_id=stored.id)

    assert FileAccessPolicy(employee).can_read(stored) is True


def test_allocation_import_file_is_supervisor_only(employee, supervisor):
    stored = FileService(actor=supervisor).store(_png_upload(), context=FileContext.ALLOCATION)
    assert FileAccessPolicy(employee).can_read(stored) is False
    assert FileAccessPolicy(supervisor).can_read(stored) is True


def test_chat_attachments_are_never_readable():
    """Chat is not implemented — the safe default is False, not a TODO."""
    from apps.accounts.models import User

    fake_owner = User(emp_id="NOBODY")
    stored = StoredFile(owner_emp_id="SOMEONE_ELSE", context=FileContext.CHAT)
    assert FileAccessPolicy(fake_owner).can_read(stored) is False


# ── HTTP: upload / download / thumbnail / delete ─────────────

def test_upload_over_http(as_employee, employee):
    response = as_employee.post(
        "/api/v1/files/", {"file": _png_upload(), "context": "misc"}, format="multipart"
    )
    assert response.status_code == 201
    assert response.data["data"]["mime_type"] == "image/png"


def test_upload_rejects_a_disguised_executable(as_employee):
    response = as_employee.post(
        "/api/v1/files/",
        {"file": SimpleUploadedFile("safe.png", b"MZ" + b"\x00" * 200, content_type="image/png"),
         "context": "misc"},
        format="multipart",
    )
    assert response.status_code == 400


def test_download_requires_permission(as_employee, other_employee):
    stored = FileService(actor=other_employee).store(_png_upload(), context=FileContext.MISC)
    response = as_employee.get(f"/api/v1/files/{stored.uuid}/")
    # 404, not 403 — existence is not something the caller has earned.
    assert response.status_code == 404


def test_download_own_file_succeeds(as_employee, employee):
    stored = FileService(actor=employee).store(_png_upload())
    response = as_employee.get(f"/api/v1/files/{stored.uuid}/")
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment")
    assert response["X-Content-Type-Options"] == "nosniff"


def test_download_unknown_uuid_is_404(as_employee):
    import uuid

    response = as_employee.get(f"/api/v1/files/{uuid.uuid4()}/")
    assert response.status_code == 404


def test_delete_over_http(as_employee, employee):
    stored = FileService(actor=employee).store(_png_upload())
    response = as_employee.delete(f"/api/v1/files/{stored.uuid}/delete/")

    assert response.status_code == 200
    assert not StoredFile.objects.filter(pk=stored.pk).exists()


def test_files_endpoints_reject_anonymous_requests(api):
    assert api.post("/api/v1/files/", {}).status_code in (401, 403)
