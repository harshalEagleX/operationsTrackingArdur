"""Celery application.

Two queues, two workers: a 90-second Excel export must never sit in front of a
notification fan-out. Queue routing lives in settings.CELERY_TASK_ROUTES.
"""

import os
from pathlib import Path

import environ
from celery import Celery
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "opstracking.settings.dev")

app = Celery("opstracking")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Default schedule. django_celery_beat stores the live schedule in the
# database, so these are the seeds — edit them in the admin after first run.
app.conf.beat_schedule = {
    "reap-stale-presence": {
        "task": "apps.presence.tasks.reap_stale_presence",
        "schedule": 30.0,
    },
    "check-break-overruns": {
        "task": "apps.breaks.tasks.check_break_overruns",
        "schedule": 60.0,
    },
    "check-sla-breaches": {
        "task": "apps.allocations.tasks.check_sla_breaches",
        "schedule": 900.0,
    },
    "prune-outbox": {
        "task": "apps.realtime.tasks.prune_outbox",
        "schedule": crontab(hour=2, minute=0),
    },
    "prune-notifications": {
        "task": "apps.notifications.tasks.prune_notifications",
        "schedule": crontab(hour=2, minute=15),
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover
    """Smoke test: `celery -A opstracking call opstracking.celery.debug_task`."""
    return f"request: {self.request!r}"
