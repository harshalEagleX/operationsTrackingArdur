from django.contrib import admin

from apps.breaks.models import BreakTime


@admin.register(BreakTime)
class BreakTimeAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user_id", "user_name", "break_type",
        "start_time", "end_time", "total_time", "allotted_time", "is_overrun",
    )
    list_filter = ("break_type", "is_overrun")
    search_fields = ("user_id", "user_name")
    date_hierarchy = "start_time"
    ordering = ("-start_time",)
    readonly_fields = ("total_time", "is_overrun")
