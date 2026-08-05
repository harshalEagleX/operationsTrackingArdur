from django.contrib import admin

from apps.realtime.models import OutboxEvent, WebSocketTicket


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ("id", "topic", "event_type", "created_at")
    list_filter = ("event_type",)
    search_fields = ("topic", "event_type")
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in OutboxEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WebSocketTicket)
class WebSocketTicketAdmin(admin.ModelAdmin):
    list_display = ("token", "emp_id", "created_at", "expires_at", "redeemed_at")
    search_fields = ("emp_id",)
    readonly_fields = [f.name for f in WebSocketTicket._meta.fields]

    def has_add_permission(self, request):
        return False
