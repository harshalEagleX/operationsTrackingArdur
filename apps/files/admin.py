from django.contrib import admin

from apps.files.models import StoredFile


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = (
        "id", "original_name", "owner_emp_id", "context",
        "mime_type", "size_display", "scan_status", "created_at",
    )
    list_filter = ("context", "scan_status", "mime_type")
    search_fields = ("original_name", "owner_emp_id", "sha256")
    date_hierarchy = "created_at"
    readonly_fields = ("uuid", "sha256", "stored_path", "thumb_path", "size_bytes")

    def has_add_permission(self, request):
        # Files are created by the upload pipeline, which validates them.
        return False
