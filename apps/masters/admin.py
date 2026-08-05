from django.contrib import admin

from apps.masters.models import ClientCode, Project, Shift, WorkType


@admin.register(WorkType)
class WorkTypeAdmin(admin.ModelAdmin):
    list_display = ("work_type", "standard_rate", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("work_type", "description")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("project_name", "project_code", "client_name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("project_name", "project_code", "client_name")


@admin.register(ClientCode)
class ClientCodeAdmin(admin.ModelAdmin):
    list_display = ("client_code", "client_name", "project", "is_active")
    list_filter = ("is_active",)
    search_fields = ("client_code", "client_name", "project")


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("shift_name", "start_time", "end_time", "break_minutes", "is_active")
    list_filter = ("is_active",)
    search_fields = ("shift_name",)
