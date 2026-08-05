"""OpsTracking project package.

Importing Django must also import the Celery app so that the ``@shared_task``
decorator in every ``apps/*/tasks.py`` binds to it.
"""

from opstracking.celery import app as celery_app

__all__ = ("celery_app",)
