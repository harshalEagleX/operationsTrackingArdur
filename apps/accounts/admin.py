from django.contrib import admin

from apps.accounts.models import Employee, LoginHistory, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("emp_id", "name", "status", "last_login")
    list_filter = ("status",)
    search_fields = ("emp_id", "name")
    readonly_fields = ("last_login", "password")
    ordering = ("emp_id",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "name", "role", "project", "shift", "status")
    list_filter = ("role", "status", "department")
    search_fields = ("employee_id", "name", "email", "project")
    ordering = ("name",)


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    list_display = ("emp_id", "name", "login_time", "logout_time", "ip_address")
    list_filter = ("date",)
    search_fields = ("emp_id", "name")
    date_hierarchy = "login_time"
    ordering = ("-login_time",)
