from django.contrib import admin

from apps.notifications.models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id", "recipient_emp_id", "notif_type", "title",
        "priority", "read_at", "created_at",
    )
    list_filter = ("notif_type", "priority")
    search_fields = ("recipient_emp_id", "title", "body")
    date_hierarchy = "created_at"
    ordering = ("-id",)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("emp_id", "notif_type", "in_app", "email")
    list_filter = ("notif_type", "in_app", "email")
    search_fields = ("emp_id",)
