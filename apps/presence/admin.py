from django.contrib import admin

from apps.presence.models import PresenceState


@admin.register(PresenceState)
class PresenceStateAdmin(admin.ModelAdmin):
    list_display = (
        "emp_id", "status", "status_source", "connection_count",
        "last_seen_at", "last_heartbeat_at",
    )
    list_filter = ("status", "status_source")
    search_fields = ("emp_id",)
    readonly_fields = ("last_seen_at", "last_heartbeat_at", "updated_at")
