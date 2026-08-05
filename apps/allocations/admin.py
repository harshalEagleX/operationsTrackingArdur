from django.contrib import admin

from apps.allocations.models import BatchAllocation, OrderHistory


@admin.register(BatchAllocation)
class BatchAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "allocation_id", "employee_id", "project", "quantity",
        "completed_quantity", "status", "priority", "due_at",
    )
    list_filter = ("status", "priority", "project")
    search_fields = ("allocation_id", "order_id", "employee_id", "batch")
    date_hierarchy = "allocated_at"
    ordering = ("-allocated_at",)


@admin.register(OrderHistory)
class OrderHistoryAdmin(admin.ModelAdmin):
    list_display = ("allocation_id", "action", "from_status", "to_status",
                    "performed_by", "created_at")
    list_filter = ("action",)
    search_fields = ("allocation_id", "order_id", "employee_id")
    date_hierarchy = "created_at"
    # An audit trail you can edit is not an audit trail.
    readonly_fields = [f.name for f in OrderHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
