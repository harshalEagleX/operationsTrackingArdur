from django.contrib import admin

from apps.settings_app.models import AppSetting


@admin.register(AppSetting)
class AppSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "value_type", "category", "is_editable", "updated_at")
    list_filter = ("category", "value_type", "is_editable")
    search_fields = ("key", "label", "description")
    readonly_fields = ("key", "value_type", "updated_by", "updated_at")
