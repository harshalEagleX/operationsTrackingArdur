from django.contrib import admin

from apps.feedback.models import Feedback, FeedbackImage


class FeedbackImageInline(admin.TabularInline):
    model = FeedbackImage
    extra = 0
    fields = ("file", "caption", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = (
        "id", "emp_id", "feedback_type", "severity", "subject",
        "created_by", "created_at", "acknowledged_at",
    )
    list_filter = ("feedback_type", "severity")
    search_fields = ("emp_id", "subject", "order_batch_id", "description")
    date_hierarchy = "created_at"
    inlines = [FeedbackImageInline]
    ordering = ("-created_at",)
