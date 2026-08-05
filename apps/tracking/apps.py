from django.apps import AppConfig


class TrackingConfig(AppConfig):
    name = "apps.tracking"
    label = "tracking"
    verbose_name = "Work tracking"

    def ready(self):
        from apps.tracking import signals  # noqa: F401
