from django.contrib import admin

from apps.reports.models import ReportJob


@admin.register(ReportJob)
class ReportJobAdmin(admin.ModelAdmin):
    list_display = (
        "id", "report_key", "requested_by", "status", "export_format",
        "row_count", "created_at", "finished_at",
    )
    list_filter = ("status", "report_key", "export_format")
    search_fields = ("requested_by", "report_key")
    date_hierarchy = "created_at"
    readonly_fields = ("started_at", "finished_at", "row_count", "file")

    def has_add_permission(self, request):
        return False
